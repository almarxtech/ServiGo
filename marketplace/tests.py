"""Ownership and CRUD regression tests for ServiGo."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import override_settings

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Booking, Service, UserProfile


class MarketplaceCrudTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.provider = User.objects.create_user(username='provider_test', password='pAssword123')
        cls.provider2 = User.objects.create_user(username='another_provider', password='pAssword123')
        cls.customer = User.objects.create_user(username='customer_test', password='pAssword123')
        cls.customer2 = User.objects.create_user(username='another_customer', password='pAssword123')
        for user, role in [(cls.provider, 'provider'), (cls.provider2, 'provider'), (cls.customer, 'customer'), (cls.customer2, 'customer')]:
            UserProfile.objects.create(user=user, role=role, phone_number='12345678', address='Testing')
        cls.service = Service.objects.create(provider=cls.provider, title='Plumbing', description='Repair pipe', price=Decimal('150.00'), category='Plumbing')
        cls.booking = Booking.objects.create(customer=cls.customer, service=cls.service, booking_date=timezone.now() + timedelta(days=5))

    def dt_value(self, days=8):
        return (timezone.localtime(timezone.now()) + timedelta(days=days)).strftime('%Y-%m-%dT%H:%M')

    def test_dashboard_renders_for_both_roles(self):
        self.client.force_login(self.provider)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('edit_service', args=[self.service.pk]))
        self.assertNotContains(response, reverse('edit_booking', args=[self.booking.pk]))
        self.assertNotContains(response, reverse('delete_booking', args=[self.booking.pk]))
        self.assertContains(response, reverse('update_booking_status', args=[self.booking.pk, 'Accepted']))
        self.client.force_login(self.customer)
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('edit_booking', args=[self.booking.pk]))
        self.assertContains(response, reverse('delete_booking', args=[self.booking.pk]))
        self.assertNotContains(response, reverse('update_booking_status', args=[self.booking.pk, 'Accepted']))

    def test_provider_can_edit_own_service(self):
        self.client.force_login(self.provider)
        response = self.client.post(reverse('edit_service', args=[self.service.pk]), {
            'title': 'Premium Plumbing', 'description': 'Better repair', 'price': '220.50', 'category': 'Plumbing',
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.service.refresh_from_db()
        self.assertEqual(self.service.title, 'Premium Plumbing')
        self.assertEqual(self.service.price, Decimal('220.50'))

    def test_other_provider_cannot_change_or_delete_service(self):
        self.client.force_login(self.provider2)
        self.assertEqual(self.client.get(reverse('edit_service', args=[self.service.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('delete_service', args=[self.service.pk])).status_code, 404)
        self.assertTrue(Service.objects.filter(pk=self.service.pk).exists())

    def test_customer_cannot_add_service(self):
        self.client.force_login(self.customer)
        response = self.client.post(reverse('add_service'), {'title': 'Bad', 'description': 'Test', 'price': '15', 'category': 'Test'})
        self.assertEqual(response.status_code, 403)

    def test_provider_cannot_remove_service_while_active_bookings_exist(self):
        self.client.force_login(self.provider)
        url = reverse('delete_service', args=[self.service.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertRedirects(self.client.post(url), reverse('dashboard'))
        self.service.refresh_from_db()
        self.assertTrue(self.service.is_active)
        self.assertTrue(Booking.objects.filter(pk=self.booking.pk).exists())

    def test_service_removal_archives_and_keeps_history(self):
        self.booking.status = 'Completed'
        self.booking.save(update_fields=['status'])
        self.client.force_login(self.provider)
        url = reverse('delete_service', args=[self.service.pk])
        self.assertRedirects(self.client.post(url), reverse('dashboard'))
        self.service.refresh_from_db()
        self.assertFalse(self.service.is_active)
        self.assertTrue(Booking.objects.filter(pk=self.booking.pk).exists())
        self.assertNotContains(self.client.get(reverse('dashboard')), reverse('edit_service', args=[self.service.pk]))
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse('book_service', args=[self.service.pk])).status_code, 404)
        self.assertContains(self.client.get(reverse('dashboard')), self.service.title)

    def test_customer_can_reschedule_own_booking(self):
        self.client.force_login(self.customer)
        response = self.client.post(reverse('edit_booking', args=[self.booking.pk]), {'booking_date': self.dt_value()})
        self.assertRedirects(response, reverse('dashboard'))
        self.booking.refresh_from_db()
        self.assertAlmostEqual((self.booking.booking_date - timezone.now()).days, 7, delta=1)

    def test_customer_cannot_reschedule_another_users_booking(self):
        self.client.force_login(self.customer2)
        self.assertEqual(self.client.get(reverse('edit_booking', args=[self.booking.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('delete_booking', args=[self.booking.pk])).status_code, 404)

    def test_booking_status_get_not_allowed_and_only_provider_can_change(self):
        url = reverse('update_booking_status', args=[self.booking.pk, 'Accepted'])
        self.client.force_login(self.provider)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'Pending')
        self.client.force_login(self.customer)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.provider)
        self.assertRedirects(self.client.post(url), reverse('dashboard'))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'Accepted')

    def test_provider_cannot_edit_or_delete_received_booking(self):
        self.client.force_login(self.provider)
        self.assertEqual(self.client.get(reverse('edit_booking', args=[self.booking.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('delete_booking', args=[self.booking.pk])).status_code, 403)
        self.assertTrue(Booking.objects.filter(pk=self.booking.pk).exists())

    def test_provider_can_complete_only_accepted_booking(self):
        self.client.force_login(self.provider)
        complete_url = reverse('update_booking_status', args=[self.booking.pk, 'Completed'])
        self.assertEqual(self.client.post(complete_url).status_code, 400)
        self.client.post(reverse('update_booking_status', args=[self.booking.pk, 'Accepted']))
        self.assertRedirects(self.client.post(complete_url), reverse('dashboard'))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'Completed')
        self.assertEqual(self.client.post(complete_url).status_code, 400)

    def test_invalid_booking_date_is_rejected(self):
        self.client.force_login(self.customer)
        response = self.client.post(reverse('edit_booking', args=[self.booking.pk]), {'booking_date': self.dt_value(days=-3)})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Please select a future date and time.')

    def test_customer_can_delete_own_booking_after_confirmation(self):
        self.client.force_login(self.customer)
        url = reverse('delete_booking', args=[self.booking.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertTrue(Booking.objects.filter(pk=self.booking.pk).exists())
        self.assertRedirects(self.client.post(url), reverse('dashboard'))
        self.assertFalse(Booking.objects.filter(pk=self.booking.pk).exists())

    def test_api_prevents_service_ownership_bypass(self):
        self.client.force_login(self.provider2)
        url = f'/api/services/{self.service.pk}/'
        self.assertEqual(self.client.patch(url, {'title': 'Hijacked'}, content_type='application/json').status_code, 403)
        self.assertEqual(self.client.delete(url).status_code, 403)

    def test_api_hides_other_customers_bookings(self):
        self.client.force_login(self.customer2)
        self.assertEqual(self.client.get(f'/api/bookings/{self.booking.pk}/').status_code, 404)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.patch(f'/api/bookings/{self.booking.pk}/', {'status': 'Completed'}, content_type='application/json').status_code, 400)

    def test_service_create_and_booking_create(self):
        self.client.force_login(self.provider)
        r = self.client.post(reverse('add_service'), {'title': 'Deep Cleaning', 'description': 'Clean everything', 'price': '250', 'category': 'Cleaning'})
        self.assertRedirects(r, reverse('dashboard'))
        new_service = Service.objects.get(title='Deep Cleaning')
        self.client.force_login(self.customer)
        r = self.client.post(reverse('book_service', args=[new_service.id]), {'booking_date': self.dt_value(), 'action': 'book', 'problem_description': 'Bathroom water dripping from a tap'})
        self.assertRedirects(r, reverse('dashboard'))
        self.assertTrue(Booking.objects.filter(service=new_service, customer=self.customer).exists())

    def test_other_pages_render(self):
        self.assertEqual(self.client.get(reverse('login')).status_code, 200)
        self.assertEqual(self.client.get(reverse('register')).status_code, 200)
        self.assertEqual(self.client.get(reverse('about')).status_code, 200)
        self.assertEqual(self.client.get(reverse('service_detail', args=[self.service.pk])).status_code, 200)
        self.client.force_login(self.customer)
        self.assertEqual(self.client.get(reverse('book_service', args=[self.service.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('profile')).status_code, 200)
        self.client.force_login(self.provider)
        self.assertEqual(self.client.get(reverse('add_service')).status_code, 200)

    def test_review_needs_completed_booking(self):
        self.client.force_login(self.customer)
        url = reverse('add_review', args=[self.service.pk])
        self.assertEqual(self.client.get(url).status_code, 403)
        self.booking.status = 'Completed'
        self.booking.save(update_fields=['status'])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertRedirects(
            self.client.post(url, {'rating': '5', 'comment': 'Great work!'}),
            reverse('service_detail', args=[self.service.pk]),
        )


class MarketplaceRoleAndAITests(MarketplaceCrudTests):
    """Extra coverage for customer/provider booking isolation and cost advice."""

    def test_customer_edit_accepted_booking_requires_new_approval(self):
        self.booking.status = 'Accepted'
        self.booking.save(update_fields=['status'])
        self.client.force_login(self.customer)
        r = self.client.post(reverse('edit_booking', args=[self.booking.pk]), {
            'booking_date': self.dt_value(),
            'problem_description': 'Water leaking from two pipes under the sink',
        })
        self.assertRedirects(r, reverse('dashboard'))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'Pending')
        self.assertIn('Water leaking', self.booking.problem_description)

    def test_customer_cannot_edit_or_delete_completed_booking(self):
        self.booking.status = 'Completed'
        self.booking.save(update_fields=['status'])
        self.client.force_login(self.customer)
        edit_url = reverse('edit_booking', args=[self.booking.pk])
        delete_url = reverse('delete_booking', args=[self.booking.pk])
        self.assertEqual(self.client.get(edit_url).status_code, 403)
        self.assertEqual(self.client.post(delete_url).status_code, 403)
        self.assertTrue(Booking.objects.filter(pk=self.booking.pk).exists())
        dashboard = self.client.get(reverse('dashboard'))
        self.assertNotContains(dashboard, edit_url)
        self.assertNotContains(dashboard, delete_url)

    def test_provider_reject_and_cannot_transition_cancelled(self):
        self.client.force_login(self.provider)
        reject_url = reverse('update_booking_status', args=[self.booking.pk, 'Cancelled'])
        self.assertRedirects(self.client.post(reject_url), reverse('dashboard'))
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'Cancelled')
        self.assertEqual(self.client.post(reverse('update_booking_status', args=[self.booking.pk, 'Accepted'])).status_code, 400)
        self.client.force_login(self.customer)
        self.assertRedirects(self.client.post(reverse('delete_booking', args=[self.booking.pk])), reverse('dashboard'))

    def test_api_provider_cannot_destroy_or_change_date(self):
        self.client.force_login(self.provider)
        url = f'/api/bookings/{self.booking.pk}/'
        self.assertEqual(self.client.delete(url).status_code, 403)
        self.assertEqual(self.client.patch(url, {'booking_date': self.dt_value()}, content_type='application/json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'status': 'Completed'}, content_type='application/json').status_code, 400)
        self.assertEqual(self.client.patch(url, {'status': 'Accepted'}, content_type='application/json').status_code, 200)
        self.assertEqual(self.client.patch(url, {'status': 'Completed'}, content_type='application/json').status_code, 200)

    def test_api_customer_accepted_date_update_resets_pending(self):
        self.booking.status = 'Accepted'
        self.booking.save(update_fields=['status'])
        self.client.force_login(self.customer)
        url = f'/api/bookings/{self.booking.pk}/'
        response = self.client.patch(url, {'booking_date': (timezone.now()+timedelta(days=8)).isoformat(),
                                           'problem_description': 'Bathroom sink dripping'}, content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'Pending')
        self.assertEqual(self.booking.problem_description, 'Bathroom sink dripping')

    @override_settings(GEMINI_API_KEY='', HF_API_KEY='')
    def test_estimate_without_key_works_and_keeps_form_values(self):
        self.client.force_login(self.customer)
        with patch('marketplace.ai_services._post_json') as mocked:
            r = self.client.post(reverse('book_service', args=[self.service.pk]), {
                'action': 'estimate', 'booking_date': self.dt_value(),
                'problem_description': 'Bathroom sink leaking and water on the floor',
            })
            mocked.assert_not_called()
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, '₹150.00')
        self.assertContains(r, '₹240.00')
        self.assertContains(r, 'Bathroom sink leaking')
        self.assertContains(r, 'Not a quotation')
        self.assertFalse(Booking.objects.filter(pk__gt=self.booking.pk).exists())

    @override_settings(GEMINI_API_KEY='', HF_API_KEY='')
    def test_estimate_rejects_too_short_details_without_booking(self):
        self.client.force_login(self.customer)
        r = self.client.post(reverse('book_service', args=[self.service.pk]), {
            'action': 'estimate', 'problem_description': 'tiny',
        })
        self.assertContains(r, 'at least 10 characters')
        self.assertEqual(Booking.objects.count(), 1)

    @override_settings(GEMINI_API_KEY='test-gemini', GEMINI_MODEL='gemini-3.5-flash-lite', HF_API_KEY='')
    def test_estimate_uses_remote_advice_without_trusting_remote_prices(self):
        self.client.force_login(self.customer)
        with patch('marketplace.ai_services._post_json', return_value={
                'candidates': [{'content': {'parts': [{'text': 'Ask for a pipe inspection first.'}]}}]
        }) as mocked:
            r = self.client.post(reverse('book_service', args=[self.service.pk]), {
                'action': 'estimate', 'problem_description': 'Kitchen sink leaking near taps',
            })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Ask for a pipe inspection first.')
        self.assertContains(r, '₹240.00')
        self.assertEqual(mocked.call_count, 1)

    @override_settings(GEMINI_API_KEY='', HF_API_KEY='')
    def test_chat_falls_back_and_clear_works(self):
        self.client.force_login(self.customer)
        r = self.client.post(reverse('ai_chat_api'),
                             data='{"message": "Can I reschedule my booking?"}',
                             content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['mode'], 'guide')
        self.assertIn('Edit', r.json()['reply'])
        self.assertEqual(len(self.client.session['chat_history']), 2)
        self.client.post(reverse('clear_chat_session'))
        self.assertNotIn('chat_history', self.client.session)

    def test_chat_input_validation(self):
        self.client.force_login(self.customer)
        url = reverse('ai_chat_api')
        self.assertEqual(self.client.post(url, data='invalid', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.post(url, data='{"message": ""}', content_type='application/json').status_code, 400)
        self.assertEqual(self.client.get(url).status_code, 405)

    @override_settings(GEMINI_API_KEY='test-gemini', HF_API_KEY='')
    def test_chat_ai_success(self):
        self.client.force_login(self.customer)
        with patch('marketplace.ai_services._post_json', return_value={
                'candidates': [{'content': {'parts': [{'text': 'You can edit your booking on the dashboard.'}]}}]
        }):
            r = self.client.post(reverse('ai_chat_api'), data='{"message": "How do I edit my booking?"}', content_type='application/json')
        self.assertEqual(r.json()['mode'], 'ai')
        self.assertIn('dashboard', r.json()['reply'])

    def test_api_archive_service_preserves_history(self):
        self.booking.status = 'Completed'
        self.booking.save(update_fields=['status'])
        self.client.force_login(self.provider)
        r = self.client.delete(f'/api/services/{self.service.pk}/')
        self.assertEqual(r.status_code, 204)
        self.service.refresh_from_db()
        self.assertFalse(self.service.is_active)
        self.assertTrue(Booking.objects.filter(pk=self.booking.pk).exists())

class AIDiagnosticTests(TestCase):
    """Error reporting should be helpful without leaking secrets to the client."""

    @override_settings(GEMINI_API_KEY='test-private-key', HF_API_KEY='')
    def test_check_ai_shows_sanitized_http_status_and_hint(self):
        from io import StringIO
        from django.core.management import call_command
        from marketplace.ai_services import AIUnavailable
        stdout = StringIO()
        with patch('marketplace.ai_services._post_json', side_effect=AIUnavailable('HTTP 403')):
            call_command('check_ai', stdout=stdout)
        diagnostic = stdout.getvalue()
        self.assertIn('Gemini: HTTP 403', diagnostic)
        self.assertIn('Possible cause: API access denied', diagnostic)
        self.assertNotIn('test-private-key', diagnostic)

    @override_settings(GEMINI_API_KEY='test-private-key', HF_API_KEY='')
    def test_chat_uses_sensible_fallback_when_ai_request_fails(self):
        from datetime import timedelta
        user = User.objects.create_user('ai_customer_test', password='12345')
        UserProfile.objects.create(user=user, role='customer', phone_number='123456', address='Test')
        self.client.force_login(user)
        from marketplace.ai_services import AIUnavailable
        with patch('marketplace.ai_services._post_json', side_effect=AIUnavailable('HTTP 403')):
            response = self.client.post(reverse('ai_chat_api'),
                data='{"message":"hi"}', content_type='application/json')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body['ai_configured'])
        self.assertEqual(body['mode'], 'guide')
        self.assertIn('key is configured', body['reply'])
        self.assertNotIn('test-private-key', str(body))

    def test_http_status_does_not_show_provider_error_body(self):
        from urllib.error import HTTPError
        from marketplace.ai_services import AIUnavailable, _post_json
        err = HTTPError('https://example.test', 401, 'private error detail', {}, None)
        with patch('marketplace.ai_services.urlopen', side_effect=err):
            with self.assertRaises(AIUnavailable) as caught:
                _post_json('https://example.test', {}, {})
        self.assertEqual(str(caught.exception), 'HTTP 401')
        self.assertNotIn('private error detail', str(caught.exception))


class MotionUIRegressionTests(TestCase):
    """Animations must not change the existing booking or AI functionality."""

    def test_motion_assets_are_available_in_staticfiles(self):
        from django.contrib.staticfiles import finders
        self.assertIsNotNone(finders.find('marketplace/motion.css'))
        self.assertIsNotNone(finders.find('marketplace/motion.js'))

    def test_base_template_loads_motion_without_authentication(self):
        response = self.client.get(reverse('login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'marketplace/motion.css')
        self.assertContains(response, 'marketplace/motion.js')
        self.assertContains(response, 'id="sgBackTop"')
        self.assertContains(response, 'id="sgScrollProgress"')

    def test_reduced_motion_and_no_javascript_fallback_are_present(self):
        from django.contrib.staticfiles import finders
        with open(finders.find('marketplace/motion.css'), encoding='utf-8') as css:
            css_source = css.read()
        with open(finders.find('marketplace/motion.js'), encoding='utf-8') as js:
            js_source = js.read()
        self.assertIn('prefers-reduced-motion: reduce', css_source)
        self.assertIn("'IntersectionObserver' in window", js_source)
        self.assertIn('sg-visible', js_source)

class VisualDashboardTests(TestCase):
    """New visual UI uses existing data; status display must match real permissions."""

    @classmethod
    def setUpTestData(cls):
        cls.provider = User.objects.create_user('visual_provider', password='good-pass-123')
        cls.customer = User.objects.create_user('visual_customer', password='good-pass-123')
        UserProfile.objects.create(user=cls.provider, role='provider', phone_number='11', address='A')
        UserProfile.objects.create(user=cls.customer, role='customer', phone_number='22', address='B')
        cls.plumber = Service.objects.create(provider=cls.provider, title='Fix kitchen sink',
                                             description='Quality plumbing work', category='Plumbing', price=Decimal('250'))
        cls.cleaner = Service.objects.create(provider=cls.provider, title='Deep clean',
                                             description='Home clean', category='Cleaning', price=Decimal('120'))
        cls.booking = Booking.objects.create(service=cls.plumber, customer=cls.customer,
                                             booking_date=timezone.now() + timedelta(days=3))

    def test_category_filter_icons_and_shortcuts_are_real(self):
        self.client.force_login(self.customer)
        res = self.client.get(reverse('dashboard'))
        self.assertContains(res, 'category-plumbing')
        self.assertContains(res, 'category-cleaning')
        self.assertContains(res, 'fa-faucet-drip')
        self.assertContains(res, 'fa-broom')
        self.assertContains(res, '?category=Plumbing#explore')
        res = self.client.get(reverse('dashboard'), {'category': 'Cleaning'})
        self.assertContains(res, 'Deep clean')
        self.assertNotContains(res, 'Fix kitchen sink</h3>')
        self.assertContains(res, 'aria-current="page"')

    def test_provider_can_see_progress_without_customer_only_controls(self):
        self.client.force_login(self.provider)
        res = self.client.get(reverse('dashboard'))
        self.assertContains(res, 'BOOKING PROGRESS')
        self.assertContains(res, 'Waiting for your approval')
        self.assertContains(res, 'aria-current="step"')
        self.assertContains(res, 'Accepted</span>')
        self.assertNotContains(res, reverse('edit_booking', args=[self.booking.pk]))
        self.assertNotContains(res, reverse('delete_booking', args=[self.booking.pk]))

    def test_customer_progress_updates_after_acceptance_and_completion(self):
        self.client.force_login(self.customer)
        r = self.client.get(reverse('dashboard'))
        self.assertContains(r, 'Waiting for provider approval')
        self.booking.status = 'Accepted'
        self.booking.save(update_fields=['status'])
        r = self.client.get(reverse('dashboard'))
        self.assertContains(r, 'Appointment confirmed')
        self.assertContains(r, 'is-connected')
        self.booking.status = 'Completed'
        self.booking.save(update_fields=['status'])
        r = self.client.get(reverse('dashboard'))
        self.assertContains(r, 'Service completed')
        self.assertNotContains(r, reverse('edit_booking', args=[self.booking.pk]))

    def test_cancelled_booking_has_distinct_honest_status(self):
        self.booking.status = 'Cancelled'
        self.booking.save(update_fields=['status'])
        self.client.force_login(self.customer)
        res = self.client.get(reverse('dashboard'))
        self.assertContains(res, 'Booking cancelled')
        self.assertNotContains(res, 'BOOKING PROGRESS')
        self.assertNotContains(res, 'Appointment confirmed')

    def test_unknown_category_uses_safe_fixed_fallback(self):
        from marketplace.templatetags.service_visuals import category_icon, category_theme
        self.assertEqual(category_theme('misc  <script>'), 'general')
        self.assertEqual(category_icon('misc  <script>'), 'fa-screwdriver-wrench')
        self.assertEqual(category_theme('AC Repair'), 'hvac')
        self.assertEqual(category_icon('Electrical Installation'), 'fa-bolt')
        self.plumber.category = 'Unknown <script>alert(1)</script>'
        self.plumber.save(update_fields=['category'])
        self.client.force_login(self.customer)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'category-general')
        self.assertNotContains(response, 'category-Unknown')
        self.assertContains(response, '&lt;script&gt;')

    def test_detail_and_booking_illustrations_use_category(self):
        self.client.force_login(self.customer)
        detail = self.client.get(reverse('service_detail', args=[self.plumber.pk]))
        booking = self.client.get(reverse('book_service', args=[self.plumber.pk]))
        self.assertContains(detail, 'service-detail-banner category-art category-plumbing')
        self.assertContains(booking, 'booking-summary-icon category-plumbing')

    def test_new_stylesheet_available_on_login_page_and_reduced_motion(self):
        from django.contrib.staticfiles import finders
        login = self.client.get(reverse('login'))
        self.assertContains(login, 'marketplace/visuals.css')
        path = finders.find('marketplace/visuals.css')
        self.assertIsNotNone(path)
        with open(path, encoding='utf-8') as handle:
            css = handle.read()
        self.assertIn('prefers-reduced-motion:reduce', css)
        self.assertIn('journey-steps', css)
