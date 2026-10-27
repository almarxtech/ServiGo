"""Access control and behavior tests for the native ServiGo staff console."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import AdvancePayment, Booking, Complaint, Review, Service, UserProfile


class CustomAdminConsoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.staff = User.objects.create_user('admin_staff', password='SecurePass123!', is_staff=True)
        cls.another_staff = User.objects.create_user('another_staff', password='SecurePass123!', is_staff=True)
        cls.customer = User.objects.create_user('customer', password='SecurePass123!')
        cls.provider = User.objects.create_user('provider', password='SecurePass123!')
        cls.other = User.objects.create_user('other_user', password='SecurePass123!')
        for user, role in ((cls.customer, 'customer'), (cls.provider, 'provider'), (cls.other, 'customer')):
            UserProfile.objects.create(user=user, role=role, phone_number='9876543210', address='Home')
        cls.service = Service.objects.create(provider=cls.provider, title='Leak Repair',
                                             category='Plumbing', description='Repair pipes', price=Decimal('1000'))
        cls.booking = Booking.objects.create(customer=cls.customer, service=cls.service, status='Accepted',
                                             booking_date=timezone.now()+timedelta(days=5))
        cls.complaint = Complaint.objects.create(submitted_by=cls.customer, category='Booking',
                                                 subject='Booking missed', description='This is a missed booking complaint')
        cls.payment = AdvancePayment.objects.create(booking=cls.booking, amount=Decimal('200'),
                                                    method='UPI', transaction_reference='UTR-TEST-1001')
        cls.review = Review.objects.create(service=cls.service, customer=cls.customer,
                                           rating=4, comment='Helpful work')

    def test_all_native_admin_pages_staff_only(self):
        names = ('admin_dashboard', 'staff_payments', 'staff_complaints', 'staff_users',
                 'staff_services', 'staff_bookings', 'staff_reviews')
        for name in names:
            url = reverse(name)
            with self.subTest(page=name):
                self.client.logout()
                self.assertEqual(self.client.get(url).status_code, 302)
                self.client.force_login(self.customer)
                self.assertEqual(self.client.get(url).status_code, 403)
                self.client.force_login(self.staff)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'Admin workspace')
                self.assertNotContains(response, 'href="/admin/')
                self.assertContains(response, reverse('staff_payments'))

    def test_dashboard_direct_links_to_every_admin_section(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('admin_dashboard'))
        for name in ('staff_payments', 'staff_complaints', 'staff_users', 'staff_services',
                     'staff_bookings', 'staff_reviews'):
            self.assertContains(response, reverse(name))
        self.assertContains(response, '₹200.00')

    def test_all_payments_paginated_and_filterable(self):
        # One payment per booking: create 19 more requests.
        for i in range(19):
            booking = Booking.objects.create(customer=self.customer, service=self.service,
                booking_date=timezone.now()+timedelta(days=5))
            AdvancePayment.objects.create(booking=booking, amount=Decimal('30'), method='UPI',
                                          transaction_reference=f'UNIQUE-REF-{i}')
        self.client.force_login(self.staff)
        first = self.client.get(reverse('staff_payments'))
        self.assertEqual(first.context['page_obj'].paginator.count, 20)
        self.assertEqual(len(first.context['page_obj'].object_list), 15)
        second = self.client.get(reverse('staff_payments'), {'page': 2})
        self.assertEqual(len(second.context['page_obj'].object_list), 5)
        filtered = self.client.get(reverse('staff_payments'), {'q': 'UTR-TEST-1001'})
        self.assertEqual(filtered.context['page_obj'].paginator.count, 1)
        self.assertContains(filtered, 'UTR-TEST-1001')

    def test_complaint_reply_on_custom_page(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('admin_review_complaint', args=[self.complaint.pk]),
                                    {'status': 'Resolved', 'admin_response': 'Issue addressed.',
                                     'next_page': 'staff_complaints'})
        self.assertRedirects(response, reverse('staff_complaints'))
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, 'Resolved')
        self.assertContains(self.client.get(reverse('staff_complaints')), 'Issue addressed.')

    def test_payment_verification_on_custom_page(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('admin_review_payment', args=[self.payment.pk]),
                                    {'action': 'Verified', 'admin_note': 'Matched bank statement',
                                     'next_page': 'staff_payments'})
        self.assertRedirects(response, reverse('staff_payments'))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'Verified')
        self.assertEqual(self.payment.reviewed_by, self.staff)
        self.assertContains(self.client.get(reverse('staff_payments')), 'Matched bank statement')
        # Attempt to downgrade verified payment must do nothing.
        self.client.post(reverse('admin_review_payment', args=[self.payment.pk]),
                         {'action': 'Rejected', 'admin_note': 'Wrong', 'next_page': 'staff_payments'})
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'Verified')

    def test_member_suspend_activate_and_admin_protection(self):
        url = reverse('staff_toggle_user', args=[self.customer.pk])
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(url, {'action': 'suspend'}).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertRedirects(self.client.post(url, {'action': 'suspend'}), reverse('staff_users'))
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)
        self.assertRedirects(self.client.post(url, {'action': 'activate'}), reverse('staff_users'))
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)
        protected = reverse('staff_toggle_user', args=[self.another_staff.pk])
        self.assertEqual(self.client.post(protected, {'action': 'suspend'}).status_code, 403)
        self.another_staff.refresh_from_db()
        self.assertTrue(self.another_staff.is_active)

    def test_service_archive_has_booking_guard_and_restore(self):
        url = reverse('staff_toggle_service', args=[self.service.pk])
        self.client.force_login(self.staff)
        self.assertRedirects(self.client.post(url, {'action': 'archive'}), reverse('staff_services'))
        self.service.refresh_from_db()
        self.assertTrue(self.service.is_active)
        self.booking.status = 'Completed'
        self.booking.save(update_fields=['status'])
        self.assertRedirects(self.client.post(url, {'action': 'archive'}), reverse('staff_services'))
        self.service.refresh_from_db()
        self.assertFalse(self.service.is_active)
        self.assertTrue(Booking.objects.filter(pk=self.booking.pk).exists())
        self.assertRedirects(self.client.post(url, {'action': 'restore'}), reverse('staff_services'))
        self.service.refresh_from_db()
        self.assertTrue(self.service.is_active)

    def test_staff_booking_status_transitions_and_audit(self):
        self.client.force_login(self.staff)
        url = reverse('staff_update_booking', args=[self.booking.pk])
        self.assertRedirects(self.client.post(url, {'status': 'Cancelled'}), reverse('staff_bookings'))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'Cancelled')
        self.assertEqual(AdvancePayment.objects.get(pk=self.payment.pk).booking, self.booking)
        self.client.post(url, {'status': 'Accepted'})
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'Cancelled')

    def test_review_moderation_post_only(self):
        url = reverse('staff_delete_review', args=[self.review.pk])
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertRedirects(self.client.post(url), reverse('staff_reviews'))
        self.assertFalse(Review.objects.filter(pk=self.review.pk).exists())

    def test_search_and_custom_page_never_redirect_externally(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('staff_users'), {'q': 'customer'}).context['page_obj'].paginator.count, 1)
        self.assertEqual(self.client.get(reverse('staff_services'), {'state': 'active'}).context['page_obj'].paginator.count, 1)
        self.assertEqual(self.client.get(reverse('staff_bookings'), {'status': 'Accepted'}).context['page_obj'].paginator.count, 1)
        response = self.client.post(reverse('admin_review_payment', args=[self.payment.pk]),
                                    {'action': 'Rejected', 'admin_note': 'Missing transfer',
                                     'next_page': 'https://example.com'})
        self.assertRedirects(response, reverse('admin_dashboard'))
