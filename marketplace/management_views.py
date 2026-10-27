"""Role-scoped support desk, manual advance requests, and the ServiGo staff workspace."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import AdvancePaymentForm, ComplaintForm
from .models import AdvancePayment, Booking, Complaint, Service, UserProfile


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
        raise PermissionDenied('Only the booking customer can request an advance payment.')
    booking = get_object_or_404(Booking.objects.select_related('service'), pk=booking_id, customer=request.user)
    if booking.status != 'Accepted':
        raise PermissionDenied('Advance requests are available only for accepted bookings.')
    existing = AdvancePayment.objects.filter(booking=booking).first()
    if existing and existing.status == 'Verified':
        messages.info(request, 'This advance is already verified. Contact admin for further changes.')
        return redirect('dashboard')

    form = AdvancePaymentForm(request.POST or None, instance=existing, booking=booking)
    if request.method == 'POST' and form.is_valid():
        # Lock the booking and its payment: two concurrent submits must not create duplicates.
        with transaction.atomic():
            booking_locked = Booking.objects.select_for_update().get(pk=booking.pk)
            if booking_locked.status != 'Accepted':
                raise PermissionDenied('This booking is no longer accepted.')
            payment = AdvancePayment.objects.select_for_update().filter(booking=booking_locked).first()
            if payment and payment.status == 'Verified':
                raise PermissionDenied('A verified advance cannot be edited by the customer.')
            clean = form.cleaned_data
            if not payment:
                payment = AdvancePayment(booking=booking_locked)
            payment.amount = clean['amount']
            payment.method = clean['method']
            payment.transaction_reference = clean['transaction_reference']
            payment.status = 'Submitted'
            payment.admin_note = ''
            payment.reviewed_by = None
            payment.reviewed_at = None
            payment.save()
        messages.success(request, 'Advance request sent to admin. This is not a successful online payment; wait for verification.')
        return redirect('dashboard')

    return render(request, 'marketplace/advance_payment.html', {
        'form': form,
        'booking': booking,
        'existing': existing,
        'payment_instructions': settings.ADVANCE_PAYMENT_INSTRUCTIONS,
    })


@login_required(login_url='login')
def admin_dashboard(request):
    _require_staff(request.user)
    complaints = Complaint.objects.select_related('submitted_by', 'booking').all()
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
        'pending_advances': payments.filter(status='Submitted').count(),
        'verified_amount': payments.filter(status='Verified').aggregate(total=Sum('amount'))['total'] or 0,
        'complaints': complaints[:20],
        'payments': payments[:20],
        'recent_bookings': bookings[:10],
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
        return redirect('admin_dashboard')
    if status == 'Resolved' and not response:
        messages.error(request, 'Add a response before resolving the complaint.')
        return redirect('admin_dashboard')
    with transaction.atomic():
        complaint = get_object_or_404(Complaint.objects.select_for_update(), pk=complaint_id)
        complaint.status = status
        complaint.admin_response = response
        complaint.reviewed_by = request.user
        complaint.reviewed_at = timezone.now()
        complaint.save()
    messages.success(request, f'Complaint #{complaint_id} updated to {status}.')
    return redirect('admin_dashboard')


@login_required(login_url='login')
@require_POST
def admin_review_payment(request, payment_id):
    _require_staff(request.user)
    action = request.POST.get('action', '')
    note = request.POST.get('admin_note', '').strip()
    if action not in ('Verified', 'Rejected') or len(note) > 1000:
        messages.error(request, 'Invalid payment decision or note.')
        return redirect('admin_dashboard')
    with transaction.atomic():
        payment = get_object_or_404(AdvancePayment.objects.select_for_update(), pk=payment_id)
        if payment.status != 'Submitted':
            messages.error(request, 'Only submitted advance requests may be reviewed.')
            return redirect('admin_dashboard')
        if action == 'Verified' and not payment.transaction_reference:
            messages.error(request, 'Require a transfer reference and independently confirm funds before verifying.')
            return redirect('admin_dashboard')
        if action == 'Rejected' and not note:
            messages.error(request, 'Give the customer a reason for rejection.')
            return redirect('admin_dashboard')
        payment.status = action
        payment.admin_note = note
        payment.reviewed_by = request.user
        payment.reviewed_at = timezone.now()
        payment.save()
    messages.success(request, f'Advance request #{payment_id}: {action}. No funds were transferred by ServiGo.')
    return redirect('admin_dashboard')
