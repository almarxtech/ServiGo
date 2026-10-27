"""Razorpay Standard Checkout integration. Never trust browser payment claims.

Use test-mode keys for academic demos. Live payments require a KYC-approved merchant.
"""
import hashlib
import hmac
import secrets
from decimal import Decimal

import requests
from django.conf import settings


class GatewayError(Exception):
    """A gateway operation failed without exposing credentials or customer details."""


def configured():
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def is_test_mode():
    return settings.RAZORPAY_KEY_ID.startswith('rzp_test_')


def paise(amount):
    cents = amount * Decimal('100')
    if cents != cents.to_integral_value() or cents <= 0:
        raise ValueError('Invalid advance amount')
    return int(cents)


def _api(method, endpoint, *, payload=None):
    if not configured():
        raise GatewayError('Razorpay is not configured. Ask admin to enable Test Mode.')
    try:
        response = requests.request(
            method, 'https://api.razorpay.com/v1/' + endpoint,
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
            json=payload, timeout=12,
        )
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise GatewayError('Payment gateway is unavailable. No charge was confirmed.') from exc


def create_order(*, booking_id, amount):
    result = _api('POST', 'orders', payload={
        'amount': paise(amount), 'currency': 'INR',
        'receipt': f'servigo-b{booking_id}-{secrets.token_hex(4)}',
        'notes': {'booking_id': str(booking_id), 'purpose': 'Advance payment'},
    })
    if not isinstance(result, dict) or not str(result.get('id', '')).startswith('order_') \
       or result.get('amount') != paise(amount) or result.get('currency') != 'INR':
        raise GatewayError('Unexpected gateway order response.')
    return result['id']


def verify_checkout_signature(order_id, payment_id, signature):
    if not configured() or not (order_id and payment_id and signature):
        return False
    digest = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(),
                      f'{order_id}|{payment_id}'.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)


def fetch_payment(payment_id):
    if not payment_id.startswith('pay_') or len(payment_id) > 100:
        raise GatewayError('Invalid payment id.')
    return _api('GET', 'payments/' + payment_id)


def is_matching_capture(data, payment):
    """Require a real captured payment for the exact stored order and amount."""
    try:
        return (data.get('status') == 'captured'
                and data.get('order_id') == payment.gateway_order_id
                and data.get('currency') == 'INR'
                and int(data.get('amount', -1)) == paise(payment.amount)
                and str(data.get('id', '')).startswith('pay_'))
    except (TypeError, ValueError):
        return False


def verify_webhook(body, signature):
    secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not secret or not signature:
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, signature)
