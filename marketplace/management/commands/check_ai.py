"""Diagnostic check for ServiGo's optional external AI assistant."""
from django.conf import settings
from django.core.management.base import BaseCommand

from marketplace.ai_services import AIUnavailable, configured_provider, generate_text


class Command(BaseCommand):
    help = 'Check optional AI configuration and perform a small AI request if configured.'

    def add_arguments(self, parser):
        parser.add_argument('--skip-call', action='store_true', help='Only check configuration, no API request.')

    def handle(self, *args, **options):
        provider = configured_provider()
        self.stdout.write(f'Primary provider: {provider or "none"}')
        self.stdout.write(f'Gemini model: {settings.GEMINI_MODEL}; HF model: {settings.HF_MODEL}')
        if not provider:
            self.stdout.write(self.style.WARNING('No AI key configured. Cost guide and support guide work without a key.'))
            return
        if options['skip_call']:
            self.stdout.write('External request skipped.')
            return
        try:
            reply, used = generate_text('Answer with one short sentence.',
                                        'Say hello to a home services customer.', max_tokens=120)
        except AIUnavailable as exc:
            # The exception contains only provider names and safe diagnostic labels,
            # never API credentials, request URLs or provider response bodies.
            self.stdout.write(self.style.ERROR(f'External AI request failed: {exc}'))
            reasons = (
                ('HTTP 400', 'Invalid request or incompatible model. Check GEMINI_MODEL / HF_MODEL.'),
                ('HTTP 401', 'Invalid or revoked API key. Create a fresh key.'),
                ('HTTP 403', 'API access denied. Check permissions, region or billing/project restrictions.'),
                ('HTTP 404', 'Model not found or unavailable to your account. Check the exact model ID.'),
                ('HTTP 429', 'API quota/rate limit reached. Check plan, quotas and billing.'),
                ('HTTP 5', 'Provider server error. Try again later.'),
                ('Network/timeout error', 'Network, DNS, proxy or firewall connectivity problem.'),
            )
            for fragment, explanation in reasons:
                if fragment in str(exc):
                    self.stdout.write(self.style.WARNING(f'Possible cause: {explanation}'))
            self.stdout.write('After changing .env, restart python manage.py runserver.')
        else:
            self.stdout.write(self.style.SUCCESS(f'{used} AI connection works.'))
            self.stdout.write(f'Model replied: {reply[:160]}')
