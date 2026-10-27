"""Gateway integration and complaint-counterparty privacy regression tests.
External Razorpay calls are stubbed; no real money or network is used.
"""
import hashlib
import hmac
import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import AdvancePayment, Booking, Complaint, Service, UserProfile


@override_settings(
    RAZORPAY_KEY_ID='rzp_test_sample_public_key',
    RAZORPAY_KEY_SECRET='server_secret_for_mock_testing',
    RAZORPAY_WEBHOOK_SECRET='test_webhook_secret',
)
class GatewayWorkflowTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user('payer', password='Valid123!')
        self.stranger = User.objects.create_user('stranger', password='Valid123!')
        self.provider = User.objects.create_user('worker', password='Valid123!')
        self.staff = User.objects.create_user('staffer', password='Valid123!', is_staff=True)
        for u, role in [(self.customer, 'customer'), (self.stranger, 'customer'), (self.provider, 'provider')]:
            UserProfile.objects.create(user=u, role=role, phone_number='12345678', address='Testing')
        self.service = Service.objects.create(provider=self.provider, title='Pipe repair',
                       category='Plumbing', description='Pipe fix', price=Decimal('500.00'))
        self.booking = Booking.objects.create(customer=self.customer, service=self.service,
                       booking_date=timezone.now() + timedelta(days=3), status='Accepted')
        self.payment_url = reverse('advance_payment', args=[self.booking.id])
        self.confirm_url = reverse('gateway_confirm', args=[self.booking.id])
        self.client.force_login(self.customer)

    def _init(self):
        with patch('marketplace.payment_gateway.create_order', return_value='order_abc123') as create:
            resp = self.client.post(self.payment_url, {'payment_flow': 'gateway', 'amount': '200.00'})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Open Razorpay checkout')
        create.assert_called_once()
        return AdvancePayment.objects.get(booking=self.booking)

    def _signature(self, order='order_abc123', pid='pay_abc123'):
        return hmac.new(b'server_secret_for_mock_testing', f'{order}|{pid}'.encode(), hashlib.sha256).hexdigest()

    def _captured(self, **overrides):
        return {'id': 'pay_abc123', 'status': 'captured', 'order_id': 'order_abc123',
                'amount': 20000, 'currency': 'INR', 'method': 'upi', **overrides}

    def test_checkout_initiation_and_reuse_same_order(self):
        record = self._init()
        self.assertEqual(record.status, 'Awaiting Payment')
        self.assertEqual(record.gateway_mode, 'test')
        self.assertEqual(record.gateway_payment_id, None)
        # Repeated click must not order the second charge.
        with patch('marketplace.payment_gateway.create_order', side_effect=AssertionError('duplicate')):
            response = self.client.post(self.payment_url, {'payment_flow': 'gateway', 'amount': '200.00'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AdvancePayment.objects.count(), 1)
        self.assertContains(response, 'order_abc123')

    def test_wrong_amount_or_permissions_prevent_checkout(self):
        with patch('marketplace.payment_gateway.create_order', side_effect=AssertionError('should not call')):
            self.assertEqual(self.client.post(self.payment_url, {'payment_flow': 'gateway', 'amount': '600.00'}).status_code, 200)
        self.assertFalse(AdvancePayment.objects.exists())
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.post(self.payment_url, {'payment_flow': 'gateway', 'amount': '20'}).status_code, 404)
        self.client.force_login(self.provider)
        self.assertEqual(self.client.get(self.payment_url).status_code, 403)

    def test_forged_signature_does_not_mark_paid(self):
        record = self._init()
        resp = self.client.post(self.confirm_url, {'razorpay_order_id': 'order_abc123',
             'razorpay_payment_id': 'pay_abc123', 'razorpay_signature': 'forged'})
        self.assertEqual(resp.status_code, 400)
        record.refresh_from_db()
        self.assertEqual(record.status, 'Awaiting Payment')

    def test_api_amount_and_capture_status_required(self):
        record = self._init()
        payload = {'razorpay_order_id': 'order_abc123', 'razorpay_payment_id': 'pay_abc123',
                   'razorpay_signature': self._signature()}
        for invalid in [self._captured(amount=19000), self._captured(status='authorized'),
                        self._captured(order_id='order_other'), self._captured(currency='USD')]:
            with patch('marketplace.payment_gateway.fetch_payment', return_value=invalid):
                response = self.client.post(self.confirm_url, payload)
            self.assertRedirects(response, reverse('dashboard'))
            record.refresh_from_db()
            self.assertEqual(record.status, 'Awaiting Payment')
        with patch('marketplace.payment_gateway.fetch_payment', return_value=self._captured()):
            resp = self.client.post(self.confirm_url, payload)
        self.assertRedirects(resp, reverse('dashboard'))
        record.refresh_from_db()
        self.assertEqual(record.status, 'Gateway Paid')
        self.assertEqual(record.gateway_method, 'upi')
        self.assertEqual(record.gateway_payment_id, 'pay_abc123')
        self.assertEqual(record.gateway_mode, 'test')

    def test_signed_webhook_and_idempotent_replay(self):
        record = self._init()
        webhook_url = reverse('gateway_webhook')
        body = json.dumps({'event': 'payment.captured', 'payload': {'payment': {'entity': self._captured()}}}).encode()
        self.assertEqual(self.client.post(webhook_url, body, content_type='application/json',
                         HTTP_X_RAZORPAY_SIGNATURE='wrong').status_code, 403)
        record.refresh_from_db()
        self.assertEqual(record.status, 'Awaiting Payment')
        signature = hmac.new(b'test_webhook_secret', body, hashlib.sha256).hexdigest()
        for _ in range(2):
            self.assertEqual(self.client.post(webhook_url, body, content_type='application/json',
                             HTTP_X_RAZORPAY_SIGNATURE=signature).status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.status, 'Gateway Paid')
        self.assertEqual(record.gateway_payment_id, 'pay_abc123')

    def test_admin_cannot_manually_verify_awaiting_gateway_payment(self):
        record = self._init()
        self.client.force_login(self.staff)
        response = self.client.post(reverse('admin_review_payment', args=[record.pk]),
            {'action': 'Verified', 'admin_note': 'Fake confirmation', 'next_page': 'staff_payments'})
        self.assertRedirects(response, reverse('staff_payments'))
        record.refresh_from_db()
        self.assertEqual(record.status, 'Awaiting Payment')

    def test_complaint_shows_both_parties_staff_only(self):
        self.client.force_login(self.customer)
        response = self.client.post(reverse('my_complaints'), {
            'booking': self.booking.id, 'category': 'Service', 'subject': 'Poor service',
            'description': 'The service provider could not finish the job properly.',
        })
        self.assertRedirects(response, reverse('my_complaints'))
        complaint = Complaint.objects.get()
        self.assertEqual(complaint.booking.service.provider, self.provider)
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse('staff_complaints')), 'Customer')
        self.assertContains(self.client.get(reverse('staff_complaints')), 'payer')
        self.assertContains(self.client.get(reverse('staff_complaints')), 'worker')
        self.client.force_login(self.stranger)
        self.assertNotContains(self.client.get(reverse('my_complaints')), 'Poor service')
        self.assertEqual(self.client.get(reverse('staff_complaints')).status_code, 403)

    def test_general_service_complaint_requires_booking_to_identify_provider(self):
        response = self.client.post(reverse('my_complaints'), {
            'category': 'Service', 'subject': 'Provider behavior',
            'description': 'I need help with the service provider behavior.',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select the related booking')
        self.assertFalse(Complaint.objects.exists())


@override_settings(RAZORPAY_KEY_ID='', RAZORPAY_KEY_SECRET='')
class UnconfiguredGatewayTests(TestCase):
    def test_empty_gateway_settings_do_not_create_a_false_payment(self):
        customer = User.objects.create_user('no_keys_customer', password='Valid123!')
        provider = User.objects.create_user('no_keys_provider', password='Valid123!')
        UserProfile.objects.create(user=customer, role='customer', phone_number='12345678', address='Test')
        UserProfile.objects.create(user=provider, role='provider', phone_number='12345678', address='Test')
        service = Service.objects.create(provider=provider, title='Clean', category='Cleaning',
                                         description='House cleaning', price=Decimal('350'))
        booking = Booking.objects.create(customer=customer, service=service, status='Accepted',
                                          booking_date=timezone.now()+timedelta(days=2))
        self.client.force_login(customer)
        resp = self.client.post(reverse('advance_payment', args=[booking.pk]),
                                {'payment_flow': 'gateway', 'amount': '120'})
        self.assertContains(resp, 'Gateway not configured')
        self.assertFalse(AdvancePayment.objects.exists())

@override_settings(RAZORPAY_KEY_ID='', RAZORPAY_KEY_SECRET='')
class ProviderComplaintCounterpartyTests(TestCase):
    def test_provider_complaint_about_customer_lists_both_in_admin(self):
        worker = User.objects.create_user('provider_john', password='Valid123!')
        buyer = User.objects.create_user('customer_maya', password='Valid123!')
        admin = User.objects.create_user('manager', password='Valid123!', is_staff=True)
        UserProfile.objects.create(user=worker, role='provider', phone_number='123', address='Town')
        UserProfile.objects.create(user=buyer, role='customer', phone_number='123', address='Town')
        service = Service.objects.create(provider=worker, title='Electrical repair',
                                         category='Electrical', description='Repair wiring', price=Decimal('700'))
        booking = Booking.objects.create(customer=buyer, service=service,
                                          booking_date=timezone.now()+timedelta(days=2), status='Accepted')
        self.client.force_login(worker)
        response = self.client.post(reverse('my_complaints'), {
            'category': 'Booking', 'booking': booking.pk, 'subject': 'Customer no show',
            'description': 'The customer did not arrive for the scheduled service appointment.',
        })
        self.assertRedirects(response, reverse('my_complaints'))
        self.client.force_login(admin)
        response = self.client.get(reverse('staff_complaints'))
        self.assertContains(response, 'provider_john')
        self.assertContains(response, 'customer_maya')
        self.assertContains(response, 'Electrical repair')
