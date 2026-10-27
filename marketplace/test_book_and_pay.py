"""Book & Pay Now regression tests (Razorpay is mocked: no network/no real money)."""
import hashlib
import hmac
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import AdvancePayment, Booking, Service, UserProfile


@override_settings(RAZORPAY_KEY_ID='rzp_test_public_mock', RAZORPAY_KEY_SECRET='test_secret')
class BookAndPayNowTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user('booking_payer', password='Secure123!')
        self.other_customer = User.objects.create_user('another_payer', password='Secure123!')
        self.provider = User.objects.create_user('booking_worker', password='Secure123!')
        for user, role in [(self.customer, 'customer'), (self.other_customer, 'customer'), (self.provider, 'provider')]:
            UserProfile.objects.create(user=user, role=role, phone_number='9999999999', address='Test')
        self.service = Service.objects.create(provider=self.provider, title='Kitchen clean',
            category='Cleaning', description='Clean kitchen', price=Decimal('450.00'))
        self.booking_url = reverse('book_service', args=[self.service.pk])
        self.client.force_login(self.customer)
        self.token = str(uuid4())
        self.fields = {'action': 'book_pay', 'booking_token': self.token, 'pay_before_approval_ack': 'yes',
                       'booking_date': (timezone.now() + timedelta(days=5)).strftime('%Y-%m-%dT%H:%M'),
                       'problem_description': 'Clean kitchen thoroughly'}

    def test_booking_page_offers_pay_now_and_later(self):
        response = self.client.get(self.booking_url)
        self.assertContains(response, 'Book &amp; Pay Now', html=False)
        self.assertContains(response, 'Book &amp; Pay Later', html=False)
        self.assertContains(response, 'booking_token')
        self.assertContains(response, 'pay_before_approval_ack')

    def test_pay_now_creates_pending_booking_and_order_in_admin(self):
        with patch('marketplace.payment_gateway.create_order', return_value='order_at_booking_1') as mocked:
            response = self.client.post(self.booking_url, self.fields)
        booking = Booking.objects.get(customer=self.customer)
        self.assertEqual(booking.status, 'Pending')
        self.assertRedirects(response, reverse('advance_payment', args=[booking.pk]))
        payment = booking.advance_payment
        self.assertEqual(payment.status, 'Awaiting Payment')
        self.assertEqual(payment.method, 'Razorpay')
        self.assertEqual(payment.amount, Decimal('450.00'))
        self.assertEqual(payment.gateway_order_id, 'order_at_booking_1')
        mocked.assert_called_once_with(booking_id=booking.pk, amount=Decimal('450.00'))
        # After redirect, checkout is ready on GET - no second order required.
        response = self.client.get(reverse('advance_payment', args=[booking.pk]))
        self.assertContains(response, 'Open Razorpay checkout')
        self.assertContains(response, 'Awaiting provider approval')

    def test_double_submit_same_token_does_not_create_a_second_order(self):
        with patch('marketplace.payment_gateway.create_order', return_value='order_reuse_123') as create:
            self.client.post(self.booking_url, self.fields)
            response = self.client.post(self.booking_url, self.fields)
        self.assertEqual(Booking.objects.count(), 1)
        self.assertEqual(AdvancePayment.objects.count(), 1)
        self.assertEqual(create.call_count, 1)
        self.assertEqual(response.status_code, 302)

    def test_invalid_gateway_rolls_back_booking_and_order(self):
        from .payment_gateway import GatewayError
        with patch('marketplace.payment_gateway.create_order', side_effect=GatewayError('No key')):
            response = self.client.post(self.booking_url, self.fields)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No booking or payment was created')
        self.assertFalse(Booking.objects.exists())
        self.assertFalse(AdvancePayment.objects.exists())

    def test_pay_later_creates_booking_without_online_charge(self):
        data = dict(self.fields, action='book')
        data.pop('pay_before_approval_ack')
        with patch('marketplace.payment_gateway.create_order', side_effect=AssertionError('no charge')):
            response = self.client.post(self.booking_url, data)
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(Booking.objects.count(), 1)
        self.assertFalse(AdvancePayment.objects.exists())
        booking = Booking.objects.get()
        self.assertContains(self.client.get(reverse('dashboard')), 'Pay now')
        self.assertEqual(self.client.get(reverse('advance_payment', args=[booking.pk])).status_code, 200)

    def test_acknowledgement_required_for_early_pay(self):
        data = dict(self.fields)
        data.pop('pay_before_approval_ack')
        resp = self.client.post(self.booking_url, data)
        self.assertContains(resp, 'Please acknowledge')
        self.assertFalse(Booking.objects.exists())

    def test_unauthorized_or_cross_customer_payment_blocked(self):
        with patch('marketplace.payment_gateway.create_order', return_value='order_secure_987'):
            self.client.post(self.booking_url, self.fields)
        booking = Booking.objects.get()
        self.client.force_login(self.other_customer)
        self.assertEqual(self.client.get(reverse('advance_payment', args=[booking.pk])).status_code, 404)
        self.client.force_login(self.provider)
        self.assertEqual(self.client.post(self.booking_url, self.fields).status_code, 403)

    def test_signature_and_capture_check_work_before_provider_acceptance(self):
        with patch('marketplace.payment_gateway.create_order', return_value='order_prepay'):
            self.client.post(self.booking_url, self.fields)
        booking = Booking.objects.get()
        callback = reverse('gateway_confirm', args=[booking.pk])
        payload = {'razorpay_order_id': 'order_prepay', 'razorpay_payment_id': 'pay_prepay', 'razorpay_signature': 'fake'}
        self.assertEqual(self.client.post(callback, payload).status_code, 400)
        self.assertEqual(booking.advance_payment.status, 'Awaiting Payment')
        payload['razorpay_signature'] = hmac.new(b'test_secret', b'order_prepay|pay_prepay', hashlib.sha256).hexdigest()
        captured = {'id': 'pay_prepay', 'order_id': 'order_prepay', 'amount': 45000,
                    'currency': 'INR', 'status': 'captured', 'method': 'upi'}
        with patch('marketplace.payment_gateway.fetch_payment', return_value=captured):
            self.assertRedirects(self.client.post(callback, payload), reverse('dashboard'))
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'Pending')
        self.assertEqual(booking.advance_payment.status, 'Gateway Paid')
        self.assertEqual(booking.advance_payment.gateway_method, 'upi')

    def test_pending_paid_booking_cancellation_keeps_audit(self):
        with patch('marketplace.payment_gateway.create_order', return_value='order_cancel'):
            self.client.post(self.booking_url, self.fields)
        booking = Booking.objects.get()
        payment = booking.advance_payment
        payment.status = 'Gateway Paid'
        payment.save(update_fields=['status'])
        self.assertRedirects(self.client.post(reverse('delete_booking', args=[booking.pk])), reverse('dashboard'))
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'Cancelled')
        self.assertTrue(AdvancePayment.objects.filter(pk=payment.pk).exists())
