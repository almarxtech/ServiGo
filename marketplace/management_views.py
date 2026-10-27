"""Role-scoped support desk, audited advances, Razorpay checkout and staff workspace."""
import json
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .forms import AdvancePaymentForm, ComplaintForm, GatewayAmountForm
from . import payment_gateway as gateway
from .models import AdvancePayment, Booking, Complaint, Review, Service, UserProfile


def _role(user):
    return getattr(getattr(user, 'userprofile', None), 'role', '')


def _require_member(user):
    if user.is_staff or _role(user) not in ('customer', 'provider'):
        raise PermissionDenied('Only customer and provider accounts can submit requests.')


def _require_staff(user):
    if not user.is_staff:
        raise PermissionDenied('This page is only available to ServiGo staff.')


@login_required(login_url='login')
def my_complaints(request):
    _require_member(request.user)
    form = ComplaintForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        complaint = form.save(commit=False)
        complaint.submitted_by = request.user
        complaint.save()
        messages.success(request, 'Complaint submitted to the admin support team.')
        return redirect('my_complaints')
    complaints = Complaint.objects.filter(submitted_by=request.user).select_related('booking', 'reviewed_by')
    return render(request, 'marketplace/my_complaints.html', {'form': form, 'complaints': complaints})


@login_required(login_url='login')
def advance_payment_view(request, booking_id):
    _require_member(request.user)
    if _role(request.user) != 'customer':
        raise PermissionDenied('Only the booking customer may make an advance payment.')
    booking = get_object_or_404(Booking.objects.select_related('service', 'service__provider'),
                                pk=booking_id, customer=request.user)
    if booking.status != 'Accepted':
        raise PermissionDenied('Advance payments are only available for accepted bookings.')
    existing = AdvancePayment.objects.filter(booking=booking).first()
    if existing and existing.status in ('Verified', 'Gateway Paid'):
        messages.info(request, 'This advance has already been confirmed. Contact support for refunds or changes.')
        return redirect('dashboard')

    checkout = None
    gateway_form = GatewayAmountForm(
        request.POST if request.method == 'POST' and request.POST.get('payment_flow') == 'gateway' else None,
        booking=booking, initial={'amount': existing.amount if existing else booking.service.price},
    )
    form = AdvancePaymentForm(
        request.POST if request.method == 'POST' and request.POST.get('payment_flow') != 'gateway' else None,
        instance=existing, booking=booking,
    )
    if request.method == 'POST' and request.POST.get('payment_flow') == 'gateway' and gateway_form.is_valid():
        if not gateway.configured():
            messages.error(request, 'Online gateway is not configured. Use manual advance request or contact admin.')
        else:
            # Reuse the existing order to prevent collecting multiple advances for one booking.
            with transaction.atomic():
                locked_booking = Booking.objects.select_for_update().get(pk=booking.pk)
                if locked_booking.status != 'Accepted':
                    raise PermissionDenied('Booking is no longer accepted.')
                payment = AdvancePayment.objects.select_for_update().filter(booking=locked_booking).first()
                if payment and payment.status in ('Verified', 'Gateway Paid'):
                    raise PermissionDenied('An advance was already confirmed.')
                amount = gateway_form.cleaned_data['amount']
                if payment and payment.status == 'Submitted':
                    gateway_form.add_error(None, 'A manual transfer request is pending admin review. Ask admin to review it before paying online.')
                elif payment and payment.gateway_order_id and payment.status == 'Awaiting Payment':
                    if payment.gateway_mode != ('test' if gateway.is_test_mode() else 'live'):
                        gateway_form.add_error(None, 'Gateway mode changed. Ask admin to reconcile the pending order.')
                    elif payment.amount != amount:
                        gateway_form.add_error('amount', 'An order is already open. Use the same amount or contact admin.')
                    else:
                        checkout = payment
                else:
                    try:
                        order_id = gateway.create_order(booking_id=booking.pk, amount=amount)
                    except gateway.GatewayError:
                        messages.error(request, 'Unable to open gateway checkout. No payment was recorded.')
                    else:
                        if not payment:
                            payment = AdvancePayment(booking=locked_booking)
                        payment.amount = amount
                        payment.method = 'Razorpay'
                        payment.transaction_reference = ''
                        payment.gateway_order_id = order_id
                        payment.gateway_payment_id = None
                        payment.gateway_method = ''
                        payment.gateway_mode = 'test' if gateway.is_test_mode() else 'live'
                        payment.status = 'Awaiting Payment'
                        payment.admin_note = ''
                        payment.reviewed_at = None
                        payment.reviewed_by = None
                        payment.save()
                        checkout = payment
    elif request.method == 'POST' and request.POST.get('payment_flow') != 'gateway' and form.is_valid():
        with transaction.atomic():
            locked_booking = Booking.objects.select_for_update().get(pk=booking.pk)
            if locked_booking.status != 'Accepted':
                raise PermissionDenied('Booking no longer accepted.')
            payment = AdvancePayment.objects.select_for_update().filter(booking=locked_booking).first()
            if payment and payment.status in ('Verified', 'Gateway Paid', 'Awaiting Payment'):
                raise PermissionDenied('This advance is already confirmed or an online order is in progress.')
            clean = form.cleaned_data
            if not payment:
                payment = AdvancePayment(booking=locked_booking)
            payment.amount = clean['amount']
            payment.method = clean['method']
            payment.transaction_reference = clean['transaction_reference']
            payment.status = 'Submitted'
            payment.admin_note = ''
            payment.reviewed_by = None
            payment.reviewed_at = None
            payment.save()
        messages.success(request, 'Manual transfer request sent to admin. No money was collected by this form.')
        return redirect('dashboard')
    return render(request, 'marketplace/advance_payment.html', {
        'form': form, 'gateway_form': gateway_form, 'booking': booking,
        'existing': existing, 'checkout': checkout,
        'gateway_enabled': gateway.configured(),
        'gateway_test_mode': gateway.is_test_mode(),
        'gateway_public_key': settings.RAZORPAY_KEY_ID if gateway.configured() else '',
        'gateway_amount_paise': gateway.paise(checkout.amount) if checkout else 0,
        'payment_instructions': settings.ADVANCE_PAYMENT_INSTRUCTIONS,
    })


@login_required(login_url='login')
@require_POST
def gateway_confirm(request, booking_id):
    """Only an authentic Razorpay signature AND captured API payment changes status."""
    _require_member(request.user)
    if _role(request.user) != 'customer':
        raise PermissionDenied
    booking = get_object_or_404(Booking, pk=booking_id, customer=request.user)
    order_id = request.POST.get('razorpay_order_id', '')
    payment_id = request.POST.get('razorpay_payment_id', '')
    signature = request.POST.get('razorpay_signature', '')
    with transaction.atomic():
        record = get_object_or_404(AdvancePayment.objects.select_for_update(), booking=booking,
                                   method='Razorpay', gateway_order_id=order_id)
        if record.status == 'Gateway Paid' and record.gateway_payment_id == payment_id:
            messages.success(request, 'Payment already confirmed.')
            return redirect('dashboard')
        if record.status != 'Awaiting Payment' or not gateway.verify_checkout_signature(record.gateway_order_id, payment_id, signature):
            return HttpResponseBadRequest('Payment verification failed. No advance was marked paid.')
        try:
            data = gateway.fetch_payment(payment_id)
        except gateway.GatewayError:
            messages.warning(request, 'Gateway status is not yet available; please retry later or contact admin.')
            return redirect('dashboard')
        if not gateway.is_matching_capture(data, record) or data.get('id') != payment_id:
            messages.warning(request, 'Payment not captured yet. The admin can review gateway status.')
            return redirect('dashboard')
        _mark_gateway_paid(record, data)
    messages.success(request, 'Gateway confirmed payment captured.' if record.gateway_mode == 'live'
                     else 'Test payment confirmed. No real money was transferred.')
    return redirect('dashboard')


def _mark_gateway_paid(record, details):
    """Caller holds a lock. All verification must occur before this function."""
    record.gateway_payment_id = details['id']
    record.gateway_method = str(details.get('method', 'unknown'))[:30]
    record.transaction_reference = details['id']
    record.status = 'Gateway Paid'
    record.save(update_fields=['gateway_payment_id', 'gateway_method', 'transaction_reference', 'status', 'updated_at'])


@csrf_exempt
@require_POST
def gateway_webhook(request):
    """Signed payment.captured events recover checkout callbacks that didn't reach Django."""
    if len(request.body) > 131072:
        return HttpResponseBadRequest('Payload too large')
    if not gateway.verify_webhook(request.body, request.headers.get('X-Razorpay-Signature', '')):
        return HttpResponse(status=403)
    try:
        event = json.loads(request.body)
    except (TypeError, ValueError):
        return HttpResponseBadRequest('Invalid payload')
    if not isinstance(event, dict) or event.get('event') != 'payment.captured':
        return HttpResponse(status=200)
    payload = event.get('payload') or {}
    payment = payload.get('payment') or {} if isinstance(payload, dict) else {}
    details = payment.get('entity') or {} if isinstance(payment, dict) else {}
    if not isinstance(details, dict):
        return HttpResponseBadRequest('Invalid payment payload')
    with transaction.atomic():
        record = AdvancePayment.objects.select_for_update().filter(
            gateway_order_id=details.get('order_id'), method='Razorpay').first()
        if not record:
            return HttpResponse(status=200)  # Unknown order: never create a payment from webhook
        if record.status == 'Gateway Paid' and record.gateway_payment_id == details.get('id'):
            return HttpResponse(status=200)
        if record.status != 'Awaiting Payment' or not gateway.is_matching_capture(details, record):
            return HttpResponse(status=200)
        _mark_gateway_paid(record, details)
    return HttpResponse(status=200)


@login_required(login_url='login')
def admin_dashboard(request):
    _require_staff(request.user)
    complaints = Complaint.objects.select_related('submitted_by', 'booking__customer', 'booking__service__provider').all()
    payments = AdvancePayment.objects.select_related('booking__customer', 'booking__service').all()
    bookings = Booking.objects.select_related('customer', 'service').order_by('-created_at')
    return render(request, 'marketplace/admin_dashboard.html', {
        'users_total': User.objects.count(),
        'customers_total': UserProfile.objects.filter(role='customer').count(),
        'providers_total': UserProfile.objects.filter(role='provider').count(),
        'services_total': Service.objects.filter(is_active=True).count(),
        'bookings_total': bookings.count(),
        'pending_bookings': bookings.filter(status='Pending').count(),
        'open_complaints': complaints.filter(status__in=['Open', 'In Review']).count(),
        'pending_advances': payments.filter(status__in=['Submitted', 'Awaiting Payment']).count(),
        'verified_amount': payments.filter(Q(status='Verified') | Q(status='Gateway Paid', gateway_mode='live')).aggregate(total=Sum('amount'))['total'] or 0,
        'test_total': payments.filter(status='Gateway Paid', gateway_mode='test').aggregate(total=Sum('amount'))['total'] or 0,
        'complaints': complaints[:6],
        'payments': payments[:6],
        'recent_bookings': bookings[:8],
    })


@login_required(login_url='login')
@require_POST
def admin_review_complaint(request, complaint_id):
    _require_staff(request.user)
    status = request.POST.get('status', '')
    response = request.POST.get('admin_response', '').strip()
    allowed = {item[0] for item in Complaint.STATUS_CHOICES}
    if status not in allowed or len(response) > 2000:
        messages.error(request, 'Invalid complaint status or response (maximum 2000 characters).')
        return redirect(_review_return_page(request, 'staff_complaints'))
    if status == 'Resolved' and not response:
        messages.error(request, 'Add a response before resolving the complaint.')
        return redirect(_review_return_page(request, 'staff_complaints'))
    with transaction.atomic():
        complaint = get_object_or_404(Complaint.objects.select_for_update(), pk=complaint_id)
        complaint.status = status
        complaint.admin_response = response
        complaint.reviewed_by = request.user
        complaint.reviewed_at = timezone.now()
        complaint.save()
    messages.success(request, f'Complaint #{complaint_id} updated to {status}.')
    return redirect(_review_return_page(request, 'staff_complaints'))


@login_required(login_url='login')
@require_POST
def admin_review_payment(request, payment_id):
    _require_staff(request.user)
    action = request.POST.get('action', '')
    note = request.POST.get('admin_note', '').strip()
    if action not in ('Verified', 'Rejected') or len(note) > 1000:
        messages.error(request, 'Invalid payment decision or note.')
        return redirect(_review_return_page(request, 'staff_payments'))
    with transaction.atomic():
        payment = get_object_or_404(AdvancePayment.objects.select_for_update(), pk=payment_id)
        if payment.status != 'Submitted':
            messages.error(request, 'Only submitted advance requests may be reviewed.')
            return redirect(_review_return_page(request, 'staff_payments'))
        if action == 'Verified' and not payment.transaction_reference:
            messages.error(request, 'Require a transfer reference and independently confirm funds before verifying.')
            return redirect(_review_return_page(request, 'staff_payments'))
        if action == 'Rejected' and not note:
            messages.error(request, 'Give the customer a reason for rejection.')
            return redirect(_review_return_page(request, 'staff_payments'))
        payment.status = action
        payment.admin_note = note
        payment.reviewed_by = request.user
        payment.reviewed_at = timezone.now()
        payment.save()
    messages.success(request, f'Advance request #{payment_id}: {action}. No funds were transferred by ServiGo.')
    return redirect(_review_return_page(request, 'staff_payments'))


# Direct admin views keep all daily operations inside the ServiGo interface.
def _review_return_page(request, page):
    """Only allow known in-app return destinations, never arbitrary external URLs."""
    return page if request.POST.get('next_page') == page else 'admin_dashboard'


def _staff_page(request, template, queryset, *, filters=None, extras=None):
    _require_staff(request.user)
    # Always paginate staff records; a large production dataset must not stall the page.
    page = Paginator(queryset, 15).get_page(request.GET.get('page'))
    context = {'page_obj': page, 'query': request.GET.get('q', '').strip()[:80]}
    if filters:
        context.update(filters)
    if extras:
        context.update(extras)
    return render(request, template, context)


@login_required(login_url='login')
def staff_payments(request):
    _require_staff(request.user)
    status = request.GET.get('status', '')
    qs = AdvancePayment.objects.select_related('booking__customer', 'booking__service', 'booking__service__provider', 'reviewed_by')
    if status in dict(AdvancePayment.STATUS_CHOICES):
        qs = qs.filter(status=status)
    else:
        status = ''
    query = request.GET.get('q', '').strip()[:80]
    if query:
        qs = qs.filter(Q(transaction_reference__icontains=query) |
                       Q(booking__customer__username__icontains=query) |
                       Q(booking__service__title__icontains=query) |
                       Q(booking__service__provider__username__icontains=query) |
                       Q(gateway_payment_id__icontains=query) | Q(gateway_order_id__icontains=query))
    return _staff_page(request, 'marketplace/staff_payments.html', qs.order_by('-created_at', '-pk'),
                       filters={'status_filter': status},
                       extras={'submitted_total': AdvancePayment.objects.filter(status='Submitted').count(),
                               'test_total': AdvancePayment.objects.filter(status='Gateway Paid', gateway_mode='test').aggregate(total=Sum('amount'))['total'] or 0,
                               'verified_total': AdvancePayment.objects.filter(Q(status='Verified') | Q(status='Gateway Paid', gateway_mode='live')).aggregate(total=Sum('amount'))['total'] or 0})


@login_required(login_url='login')
def staff_complaints(request):
    _require_staff(request.user)
    status = request.GET.get('status', '')
    qs = Complaint.objects.select_related('submitted_by', 'booking__customer', 'booking__service__provider', 'reviewed_by')
    if status in dict(Complaint.STATUS_CHOICES):
        qs = qs.filter(status=status)
    else:
        status = ''
    query = request.GET.get('q', '').strip()[:80]
    if query:
        qs = qs.filter(Q(subject__icontains=query) | Q(description__icontains=query) |
                       Q(submitted_by__username__icontains=query) |
                       Q(booking__customer__username__icontains=query) |
                       Q(booking__service__provider__username__icontains=query) |
                       Q(booking__service__title__icontains=query))
    return _staff_page(request, 'marketplace/staff_complaints.html', qs.order_by('-created_at', '-pk'),
                       filters={'status_filter': status})


@login_required(login_url='login')
def staff_users(request):
    _require_staff(request.user)
    role = request.GET.get('role', '')
    qs = User.objects.select_related('userprofile')
    if role in ('customer', 'provider'):
        qs = qs.filter(userprofile__role=role)
    elif role == 'staff':
        qs = qs.filter(is_staff=True)
    else:
        role = ''
    query = request.GET.get('q', '').strip()[:80]
    if query:
        qs = qs.filter(Q(username__icontains=query) | Q(email__icontains=query) |
                       Q(first_name__icontains=query) | Q(last_name__icontains=query))
    return _staff_page(request, 'marketplace/staff_users.html', qs.order_by('-date_joined', '-pk'),
                       filters={'role_filter': role})


@login_required(login_url='login')
@require_POST
def staff_toggle_user(request, user_id):
    _require_staff(request.user)
    action = request.POST.get('action')
    if action not in ('activate', 'suspend'):
        messages.error(request, 'Invalid user action.')
        return redirect('staff_users')
    with transaction.atomic():
        target = get_object_or_404(User.objects.select_for_update(), pk=user_id)
        # Never suspend administrators or the acting account through the staff UI.
        if target.is_staff or target.is_superuser or target == request.user:
            raise PermissionDenied('Staff and admin accounts cannot be changed here.')
        target.is_active = action == 'activate'
        target.save(update_fields=['is_active'])
    messages.success(request, f'Account {target.username} {"enabled" if target.is_active else "suspended"}.')
    return redirect('staff_users')


@login_required(login_url='login')
def staff_services(request):
    _require_staff(request.user)
    state = request.GET.get('state', '')
    qs = Service.objects.select_related('provider')
    if state == 'active':
        qs = qs.filter(is_active=True)
    elif state == 'archived':
        qs = qs.filter(is_active=False)
    else:
        state = ''
    query = request.GET.get('q', '').strip()[:80]
    if query:
        qs = qs.filter(Q(title__icontains=query) | Q(category__icontains=query) |
                       Q(provider__username__icontains=query))
    return _staff_page(request, 'marketplace/staff_services.html', qs.order_by('-created_at', '-pk'),
                       filters={'state_filter': state})


@login_required(login_url='login')
@require_POST
def staff_toggle_service(request, service_id):
    _require_staff(request.user)
    action = request.POST.get('action')
    if action not in ('archive', 'restore'):
        messages.error(request, 'Invalid service action.')
        return redirect('staff_services')
    with transaction.atomic():
        service = get_object_or_404(Service.objects.select_for_update(), pk=service_id)
        if action == 'archive' and Booking.objects.filter(service=service, status__in=('Pending', 'Accepted')).exists():
            messages.error(request, 'Resolve pending or accepted bookings before archiving the service.')
            return redirect('staff_services')
        service.is_active = action == 'restore'
        service.save(update_fields=['is_active'])
    messages.success(request, f'Service {service.title} {"restored" if service.is_active else "archived"}. Booking history is preserved.')
    return redirect('staff_services')


@login_required(login_url='login')
def staff_bookings(request):
    _require_staff(request.user)
    status = request.GET.get('status', '')
    qs = Booking.objects.select_related('customer', 'service', 'service__provider')
    if status in dict(Booking.STATUS_CHOICES):
        qs = qs.filter(status=status)
    else:
        status = ''
    query = request.GET.get('q', '').strip()[:80]
    if query:
        qs = qs.filter(Q(customer__username__icontains=query) |
                       Q(service__title__icontains=query) |
                       Q(service__provider__username__icontains=query))
    return _staff_page(request, 'marketplace/staff_bookings.html', qs.order_by('-created_at', '-pk'),
                       filters={'status_filter': status})


@login_required(login_url='login')
@require_POST
def staff_update_booking(request, booking_id):
    _require_staff(request.user)
    new_status = request.POST.get('status', '')
    allowed = {'Pending': ('Accepted', 'Cancelled'),
               'Accepted': ('Completed', 'Cancelled')}
    with transaction.atomic():
        booking = get_object_or_404(Booking.objects.select_for_update(), pk=booking_id)
        if new_status not in allowed.get(booking.status, ()):
            messages.error(request, 'This booking status change is not allowed.')
            return redirect('staff_bookings')
        booking.status = new_status
        booking.save(update_fields=['status'])
    # Notifications are best-effort; booking data has already been committed.
    from .views import _notify_booking
    _notify_booking(booking)
    if new_status == 'Cancelled' and AdvancePayment.objects.filter(booking=booking, status__in=['Verified', 'Gateway Paid']).exists():
        messages.warning(request, 'Booking cancelled. A verified advance may require a manual refund; none was issued automatically.')
    else:
        messages.success(request, f'Booking #{booking.id} changed to {new_status}.')
    return redirect('staff_bookings')


@login_required(login_url='login')
def staff_reviews(request):
    _require_staff(request.user)
    qs = Review.objects.select_related('customer', 'service')
    query = request.GET.get('q', '').strip()[:80]
    if query:
        qs = qs.filter(Q(comment__icontains=query) | Q(customer__username__icontains=query) |
                       Q(service__title__icontains=query))
    return _staff_page(request, 'marketplace/staff_reviews.html', qs.order_by('-created_at', '-pk'))


@login_required(login_url='login')
@require_POST
def staff_delete_review(request, review_id):
    _require_staff(request.user)
    review = get_object_or_404(Review, pk=review_id)
    review.delete()
    messages.success(request, f'Review #{review_id} removed from public listings.')
    return redirect('staff_reviews')
