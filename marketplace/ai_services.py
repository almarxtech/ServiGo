"""Provider-grounded estimates and optional text assistants.

No AI provider is required for a usable cost estimate. Remote requests are bounded,
server-side only, and no secrets are returned to the browser.
"""
import json
import logging
from decimal import Decimal, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)


class AIUnavailable(Exception):
    """Remote model unavailable or misconfigured. Do not leak provider messages to users."""


def configured_provider():
    if getattr(settings, 'GEMINI_API_KEY', '').strip():
        return 'gemini'
    if getattr(settings, 'HF_API_KEY', '').strip():
        return 'huggingface'
    return None


def _post_json(url, payload, headers, timeout=12):
    request = Request(url, data=json.dumps(payload).encode('utf-8'), headers={
        'Content-Type': 'application/json', **headers}, method='POST')
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except HTTPError as exc:
        # Do not print response bodies, URLs containing credentials, or request headers.
        # Only an HTTP status is included in diagnostics.
        logger.warning('AI provider returned HTTP %s', exc.code)
        raise AIUnavailable(f'HTTP {exc.code}') from exc
    except (URLError, TimeoutError, OSError) as exc:
        logger.warning('AI provider network request failed: %s', type(exc).__name__)
        raise AIUnavailable('Network/timeout error') from exc
    except ValueError as exc:
        logger.warning('AI provider returned invalid JSON')
        raise AIUnavailable('Invalid JSON response') from exc


def generate_text(system_prompt, user_text, history=None, max_tokens=400):
    """Try Gemini first, then Hugging Face. Raises AIUnavailable if none work."""
    history = (history or [])[-6:]
    last_error = None
    attempts = []
    gemini_key = getattr(settings, 'GEMINI_API_KEY', '').strip()
    if gemini_key:
        model = getattr(settings, 'GEMINI_MODEL', 'gemini-3.5-flash-lite')
        # Avoid URL injection from a value in a deployment config.
        if not all(char.isalnum() or char in '.-_' for char in model):
            raise AIUnavailable('Invalid model configuration')
        contents = [{'role': 'model' if item['role'] == 'assistant' else 'user',
                     'parts': [{'text': item['content'][:1200]}]} for item in history]
        contents.append({'role': 'user', 'parts': [{'text': user_text[:3000]}]})
        try:
            result = _post_json(
                f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                {'systemInstruction': {'parts': [{'text': system_prompt}]},
                 'contents': contents, 'generationConfig': {'maxOutputTokens': max_tokens}},
                {'x-goog-api-key': gemini_key},
            )
            parts = result['candidates'][0]['content']['parts']
            reply = '\n'.join(part.get('text', '') for part in parts).strip()
            if reply:
                return reply[:3000], 'gemini'
            raise AIUnavailable('Empty AI result')
        except (AIUnavailable, KeyError, IndexError, TypeError) as exc:
            last_error = exc
            attempts.append(f'Gemini: {exc}' if isinstance(exc, AIUnavailable) else 'Gemini: invalid response format')
            logger.warning('Gemini response unavailable: %s', type(exc).__name__)

    hf_key = getattr(settings, 'HF_API_KEY', '').strip()
    if hf_key:
        model = getattr(settings, 'HF_MODEL', 'openai/gpt-oss-120b:fastest')
        try:
            messages = [{'role': 'system', 'content': system_prompt}]
            messages += [{'role': turn['role'], 'content': turn['content'][:1200]} for turn in history]
            messages.append({'role': 'user', 'content': user_text[:3000]})
            result = _post_json(
                'https://router.huggingface.co/v1/chat/completions',
                {'model': model, 'messages': messages, 'max_tokens': max_tokens},
                {'Authorization': f'Bearer {hf_key}'},
            )
            reply = result['choices'][0]['message']['content']
            if isinstance(reply, str) and reply.strip():
                return reply.strip()[:3000], 'huggingface'
            raise AIUnavailable('Empty AI result')
        except (AIUnavailable, KeyError, IndexError, TypeError) as exc:
            last_error = exc
            attempts.append(f'Hugging Face: {exc}' if isinstance(exc, AIUnavailable) else 'Hugging Face: invalid response format')
            logger.warning('Hugging Face response unavailable: %s', type(exc).__name__)

    if not (gemini_key or hf_key):
        raise AIUnavailable('No API key is configured')
    raise AIUnavailable('; '.join(attempts) or 'AI provider unavailable') from last_error


def _round_money(value):
    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def get_ai_cost_estimate(notes, service):
    """A clearly labeled *illustrative* range anchored to listed service pricing.

    This is not a market-rate quote, a trained pricing model, or a provider commitment.
    AI provides optional practical advice, NEVER controls the numeric price band.
    """
    details = (notes or '').strip()[:1500]
    if len(details) < 10:
        raise ValueError('Please describe your issue in at least 10 characters.')

    text = details.casefold()
    factors = {
        'complex': ('major', 'multiple', 'severe', 'rewiring', 'replacement', 'renovation',
                    'water damage', 'large', 'full house', 'urgent', 'emergency', 'wiring',
                    'മുഴുവൻ', 'വലിയ', 'அவசரம்'),
        'medium': ('leak', 'blocked', 'clog', 'short circuit', 'fault', 'broken', 'repair',
                   'stain', 'mold', 'drain', 'pipe', 'leaking', 'തകരാർ', 'ചോർച്ച'),
    }
    if any(word in text for word in factors['complex']):
        level, multiplier = 'Complex', Decimal('2.00')
    elif any(word in text for word in factors['medium']) or len(details) > 170:
        level, multiplier = 'Moderate', Decimal('1.60')
    else:
        level, multiplier = 'Standard', Decimal('1.30')
    base = service.price
    estimate = {
        'min_price': _round_money(base),
        'max_price': _round_money(base * multiplier),
        'base_price': _round_money(base),
        'level': level,
        'source': 'guide',
        'insight': 'Ask the provider about inspection, materials, travel charges and any extra work before confirming the final price.',
        'notice': 'Illustrative range based on this provider’s listed starting price and broad job complexity. Not a verified market price or final quotation.',
    }
    if configured_provider():
        prompt = ('You are a careful home-service assistant. Write 2-3 concise, specific, useful '
                  'sentences of practical advice for a service customer about likely inspection needs, '
                  'preparation and factors that change the quote. Never invent price numbers, promise '
                  'a fix, offer unsafe electrical/gas instructions, or call an estimate guaranteed. '
                  'Reply in the user’s language when possible.')
        try:
            insight, _ = generate_text(
                prompt, f'Service: {service.title}. Category: {service.category}. '
                        f'Description: {service.description[:600]}. Customer issue: {details}', max_tokens=250)
            estimate.update({'source': 'ai', 'insight': insight})
        except AIUnavailable:
            estimate['notice'] += ' AI advice is temporarily unavailable; standard guidance is shown.'
    else:
        estimate['notice'] += ' Add an AI API key in .env for personalized AI guidance.'
    return estimate


def fallback_chat_reply(message, role, service_count, booking_count, ai_configured=False):
    """Useful, clearly non-AI help when no key works."""
    text = message.casefold()
    if any(word in text for word in ('estimate', 'cost', 'price', 'rate', 'charge', '₹', 'ചെലവ്')):
        return 'Open a service and choose Book now. Describe the issue under Cost estimate to see a guide based on that provider’s listed price. Final charges are confirmed by the provider.'
    if any(word in text for word in ('cancel', 'delete', 'remove', 'റദ്ദ്')):
        return ('Under My bookings, you can delete an eligible booking; completed bookings are kept as history.'
                if role == 'customer' else 'Under Received bookings, use Reject to cancel an uncompleted request. Providers cannot delete customers’ bookings.')
    if any(word in text for word in ('edit', 'reschedul', 'date', 'time', 'change', 'ബുക്കിംഗ്')):
        return ('Open My bookings and choose Edit on a Pending or Accepted booking to change the date. An accepted appointment goes back to Pending for provider review.'
                if role == 'customer' else 'Providers can Accept, Reject, and mark Accepted bookings Completed. Customers control their own appointment edits.')
    if any(word in text for word in ('service', 'plumb', 'clean', 'electric', 'book', 'repair')):
        return (f'There are currently {service_count} service listings. Explore services to see details and choose Book now.'
                if role == 'customer' else 'Add or edit your own service listings in Manage your services. Received customer bookings appear above.')
    status = ('Your AI key is configured, but the provider request failed. Run python manage.py check_ai '
              'in the server terminal to find the HTTP status.' if ai_configured else
              'To enable personalized AI answers, configure GEMINI_API_KEY or HF_API_KEY in your server .env.')
    return (f'I can guide you through services, bookings, rescheduling and estimates. '
            f'You have {booking_count} bookings visible in your dashboard. {status}')
