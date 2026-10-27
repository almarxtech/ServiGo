"""Admin dashboard, customer/provider complaint, and advance audit/regression tests."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AdvancePayment, Booking, Complaint, Service, UserProfile


class ServiGoManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.customer = User.objects.create_user(username='alice', password='validTest123!')
        cls.other = User.objects.create_user(username='bob', password='validTest123!')
        cls.provider = User.objects.create_user(username='plumber', password='validTest123!')
        cls.another_provider = User.objects.create_user(username='electrician', password='validTest123!')
        cls.staff = User.objects.create_user(username='staff', password='validTest123!', is_staff=True)
        for user, role in [(cls.customer, 'customer'), (cls.other, 'customer'),
                           (cls.provider, 'provider'), (cls.another_provider, 'provider')]:
            UserProfile.objects.create(user=user, role=role, phone_number='12345678', address='Test')
        cls.service = Service.objects.create(provider=cls.provider, title='Repair', category='Plumbing', description='Repair pipes', price=Decimal('600.00'))
        cls.booking = Booking.objects.create(customer=cls.customer, service=cls.service,
            booking_date=timezone.now()+timedelta(days=5), status='Accepted')

    def complaint_data(self, **extra):
        return {'category': 'Booking', 'subject': 'Appointment missed',
                'description': 'The booked service was missed and I need assistance.', **extra}

    def advance_data(self, **extra):
        return {'amount': '120.00', 'method': 'UPI', 'transaction_reference': 'TRX-01234', **extra}

    def submit_advance(self, **extra):
        self.client.force_login(self.customer)
        return self.client.post(reverse('advance_payment', args=[self.booking.id]), self.advance_data(**extra))

    def test_admin_dashboard_staff_only_no_spurious_profile(self):
        url = reverse('admin_dashboard')
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.provider)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('dashboard')).status_code, 302)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Admin workspace')
        self.assertFalse(UserProfile.objects.filter(user=self.staff).exists())

    def test_customer_and_provider_can_submit_general_complaint(self):
        for user in (self.customer, self.provider):
            self.client.force_login(user)
            response = self.client.post(reverse('my_complaints'), self.complaint_data(category='Other'))
            self.assertRedirects(response, reverse('my_complaints'))
            complaint = Complaint.objects.filter(submitted_by=user).get()
            self.assertEqual(complaint.status, 'Open')
            self.assertIsNone(complaint.booking)
            self.assertContains(self.client.get(reverse('my_complaints')), complaint.subject)
        self.assertEqual(Complaint.objects.count(), 2)

    def test_complaint_history_is_private(self):
        Complaint.objects.create(submitted_by=self.customer, subject='Private issue',
            description='A very long description of this private issue', category='Other')
        self.client.force_login(self.other)
        response = self.client.get(reverse('my_complaints'))
        self.assertNotContains(response, 'Private issue')
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('my_complaints')).status_code, 403)

    def test_cannot_attach_others_booking_to_complaint(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse('my_complaints'), self.complaint_data(booking=self.booking.pk))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Select a valid choice')
        self.assertFalse(Complaint.objects.exists())

    def test_provider_can_attach_booking_of_own_service(self):
        self.client.force_login(self.provider)
        response = self.client.post(reverse('my_complaints'), self.complaint_data(booking=self.booking.pk))
        self.assertRedirects(response, reverse('my_complaints'))
        self.assertEqual(Complaint.objects.get().booking, self.booking)

    def test_other_provider_cannot_attach_booking(self):
        self.client.force_login(self.another_provider)
        response = self.client.post(reverse('my_complaints'), self.complaint_data(booking=self.booking.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Complaint.objects.count(), 0)

    def test_complaint_validation(self):
        self.client.force_login(self.customer)
        response = self.client.post(reverse('my_complaints'), self.complaint_data(subject='x', description='Too short'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Complaint.objects.exists())

    def test_admin_complaint_review_requires_staff_and_post(self):
        complaint = Complaint.objects.create(submitted_by=self.customer, category='Account',
            subject='Login problem', description='Need help signing in right now.')
        url = reverse('admin_review_complaint', args=[complaint.pk])
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(url, {'status': 'Resolved', 'admin_response': 'Reset account password.'}).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertRedirects(self.client.post(url, {'status': 'Resolved', 'admin_response': 'Reset account password.'}), reverse('admin_dashboard'))
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, 'Resolved')
        self.assertEqual(complaint.reviewed_by, self.staff)
        self.client.force_login(self.customer)
        self.assertContains(self.client.get(reverse('my_complaints')), 'Reset account password.')

    def test_admin_complaint_cannot_resolve_without_reply_or_invalid_status(self):
        complaint = Complaint.objects.create(submitted_by=self.customer, category='Other',
            subject='Long issue', description='Some detailed problem occurred yesterday.')
        url = reverse('admin_review_complaint', args=[complaint.pk])
        self.client.force_login(self.staff)
        self.client.post(url, {'status': 'Resolved', 'admin_response': ''})
        self.client.post(url, {'status': 'Invalid', 'admin_response': 'Message'})
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, 'Open')

    def test_advance_available_for_pending_booking_before_acceptance(self):
        self.booking.status = 'Pending'
        self.booking.save(update_fields=['status'])
        self.client.force_login(self.customer)
        url = reverse('advance_payment', args=[self.booking.pk])
        self.assertContains(self.client.get(url), 'Awaiting provider approval')
        self.assertRedirects(self.client.post(url, self.advance_data()), reverse('dashboard'))
        payment = AdvancePayment.objects.get(booking=self.booking)
        self.assertEqual(payment.status, 'Submitted')
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'Pending')

    def test_advance_only_own_customer_booking(self):
        url = reverse('advance_payment', args=[self.booking.pk])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.provider)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_advance_record_is_not_auto_paid(self):
        self.assertRedirects(self.submit_advance(), reverse('dashboard'))
        payment = AdvancePayment.objects.get(booking=self.booking)
        self.assertEqual(payment.amount, Decimal('120.00'))
        self.assertEqual(payment.status, 'Submitted')
        self.assertIsNone(payment.reviewed_at)
        self.assertContains(self.client.get(reverse('dashboard')), 'Advance: Submitted')

    def test_advance_amount_validated(self):
        for invalid in ('0', '-50', '600.01'):
            self.client.force_login(self.customer)
            response = self.client.post(reverse('advance_payment', args=[self.booking.pk]), self.advance_data(amount=invalid))
            self.assertEqual(response.status_code, 200)
            self.assertFalse(AdvancePayment.objects.exists())

    def test_request_may_have_no_reference_but_cannot_verify(self):
        self.submit_advance(transaction_reference='')
        payment = AdvancePayment.objects.get()
        url = reverse('admin_review_payment', args=[payment.pk])
        self.client.force_login(self.staff)
        self.assertRedirects(self.client.post(url, {'action': 'Verified'}), reverse('admin_dashboard'))
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'Submitted')

    def test_request_can_be_updated_without_duplicate(self):
        self.submit_advance(transaction_reference='')
        self.submit_advance(amount='240', transaction_reference='NEW-REF')
        self.assertEqual(AdvancePayment.objects.count(), 1)
        self.assertEqual(AdvancePayment.objects.get().amount, Decimal('240'))

    def test_staff_can_verify_only_submitted_payment(self):
        self.submit_advance()
        payment = AdvancePayment.objects.get()
        url = reverse('admin_review_payment', args=[payment.pk])
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(url, {'action': 'Verified'}).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertRedirects(self.client.post(url, {'action': 'Verified', 'admin_note': 'Confirmed receipt'}), reverse('admin_dashboard'))
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'Verified')
        self.assertEqual(payment.reviewed_by, self.staff)
        self.assertIsNotNone(payment.reviewed_at)
        self.assertContains(self.client.get(reverse('admin_dashboard')), '120.00')
        self.assertRedirects(self.client.post(url, {'action': 'Rejected', 'admin_note': 'No'}), reverse('admin_dashboard'))
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'Verified')
        self.client.force_login(self.customer)
        self.assertRedirects(self.client.get(reverse('advance_payment', args=[self.booking.pk])), reverse('dashboard'))

    def test_admin_must_explain_payment_rejection(self):
        self.submit_advance()
        payment = AdvancePayment.objects.get()
        self.client.force_login(self.staff)
        url = reverse('admin_review_payment', args=[payment.pk])
        self.client.post(url, {'action': 'Rejected', 'admin_note': '   '})
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'Submitted')
        self.client.post(url, {'action': 'Rejected', 'admin_note': 'Reference not found'})
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'Rejected')
        self.client.force_login(self.customer)
        self.assertContains(self.client.get(reverse('advance_payment', args=[self.booking.pk])), 'Reference not found')
        self.submit_advance(transaction_reference='CORRECTED-REF')
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'Submitted')
        self.assertEqual(payment.transaction_reference, 'CORRECTED-REF')

    def test_advance_audit_is_preserved_on_web_booking_delete(self):
        self.submit_advance()
        url = reverse('delete_booking', args=[self.booking.pk])
        self.client.force_login(self.customer)
        self.assertContains(self.client.get(url), 'cancelled and kept in history')
        self.assertRedirects(self.client.post(url), reverse('dashboard'))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'Cancelled')
        self.assertEqual(AdvancePayment.objects.get().booking, self.booking)

    def test_advance_audit_is_preserved_on_api_booking_delete(self):
        self.submit_advance()
        self.client.force_login(self.customer)
        self.assertEqual(self.client.delete(f'/api/bookings/{self.booking.pk}/').status_code, 204)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'Cancelled')
        self.assertEqual(AdvancePayment.objects.count(), 1)

    def test_customer_without_advance_can_delete_booking_normally(self):
        self.client.force_login(self.customer)
        self.assertRedirects(self.client.post(reverse('delete_booking', args=[self.booking.pk])), reverse('dashboard'))
        self.assertFalse(Booking.objects.filter(pk=self.booking.pk).exists())

    def test_registration_still_works_with_multiple_backends(self):
        self.client.logout()
        response = self.client.post(reverse('register'), {
            'username': 'new_registration', 'email': 'new@example.com',
            'password': 'LongSafePass123!', 'role': 'customer',
            'phone_number': '9876543210', 'address': 'Home street',
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue(User.objects.filter(username='new_registration').exists())
        self.assertEqual(self.client.session.get('_auth_user_backend'), 'django.contrib.auth.backends.ModelBackend')
