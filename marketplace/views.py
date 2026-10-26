import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db.models import Q
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import BookingDateForm, ServiceForm, UserRegistrationForm
from .models import Booking, Review, Service, UserProfile
from .ai_services import (AIUnavailable, configured_provider, fallback_chat_reply,
                          generate_text, get_ai_cost_estimate)


def _role(request):
    return getattr(getattr(request.user, 'userprofile', None), 'role', '')


def _ensure_role(request, role):
    if _role(request) != role:
        raise PermissionDenied('You do not have permission to perform this action.')


def _notify_booking(booking):
    if booking.customer.email:
        send_mail(
            subject=f'Booking update: {booking.service.title}',
            message=(f'Hello {booking.customer.username},\n\nYour booking for '
                     f'{booking.service.title} is {booking.status}.\n'
                     f'Scheduled for: {booking.booking_date:%d %b %Y, %I:%M %p}.'),
            from_email='noreply@servigo.local',
            recipient_list=[booking.customer.email],
            fail_silently=True,
        )


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = UserRegistrationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save(commit=False)
        user.set_password(form.cleaned_data['password'])
        user.save()
        UserProfile.objects.create(
            user=user,
            role=form.cleaned_data['role'],
            phone_number=form.cleaned_data['phone_number'],
            address=form.cleaned_data['address'],
        )
        login(
            request,
            user,
            backend="django.contrib.auth.backends.ModelBackend"
        )
        messages.success(request, 'Your ServiGo account is ready. Welcome!')
        return redirect('dashboard')
    return render(request, 'marketplace/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        messages.success(request, 'Welcome back!')
        return redirect('dashboard')
    return render(request, 'marketplace/login.html', {'form': form})


@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required(login_url='login')
def dashboard_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user, defaults={'role': 'customer'})
    query = request.GET.get('q', '').strip()
    category_filter = request.GET.get('category', '').strip()
    services = Service.objects.filter(is_active=True).select_related('provider').order_by('-created_at')
    if query:
        services = services.filter(Q(title__icontains=query) | Q(description__icontains=query) | Q(category__icontains=query))
    if category_filter:
        services = services.filter(category__iexact=category_filter)

    if profile.role == 'provider':
        my_services = Service.objects.filter(provider=request.user, is_active=True).order_by('-created_at')
        bookings = Booking.objects.filter(service__provider=request.user).select_related('service', 'customer').order_by('-created_at')
        service_total = my_services.count()
    else:
        my_services = None
        bookings = Booking.objects.filter(customer=request.user).select_related('service', 'service__provider').order_by('-created_at')
        service_total = Service.objects.filter(is_active=True).count()

    return render(request, 'marketplace/dashboard.html', {
        'profile': profile,
        'services': services,
        'bookings': bookings,
        'my_services': my_services,
        'categories': Service.objects.filter(is_active=True).order_by('category').values_list('category', flat=True).distinct(),
        'query': query,
        'selected_category': category_filter,
        'service_total': service_total,
        'bookings_total': bookings.count(),
        'pending_total': bookings.filter(status='Pending').count(),
        'completed_total': bookings.filter(status='Completed').count(),
    })


@login_required(login_url='login')
def add_service_view(request):
    _ensure_role(request, 'provider')
    form = ServiceForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        service = form.save(commit=False)
        service.provider = request.user
        service.save()
        messages.success(request, 'Your service has been published.')
        return redirect('dashboard')
    return render(request, 'marketplace/add_service.html', {'form': form, 'is_edit': False})


@login_required(login_url='login')
def edit_service_view(request, service_id):
    _ensure_role(request, 'provider')
    service = get_object_or_404(Service, pk=service_id, provider=request.user, is_active=True)
    form = ServiceForm(request.POST or None, instance=service)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Service updated successfully.')
        return redirect('dashboard')
    return render(request, 'marketplace/add_service.html', {'form': form, 'is_edit': True, 'service': service})


@login_required(login_url='login')
def delete_service_view(request, service_id):
    _ensure_role(request, 'provider')
    service = get_object_or_404(Service, pk=service_id, provider=request.user, is_active=True)
    live_bookings = service.booking_set.filter(status__in=('Pending', 'Accepted')).count()
    if request.method == 'POST':
        if live_bookings:
            messages.error(request, 'Resolve pending or accepted bookings before removing this service.')
            return redirect('dashboard')
        # Archive, rather than cascade-delete customer booking/review history.
        service.is_active = False
        service.save(update_fields=['is_active'])
        messages.success(request, 'Service removed from listings. Existing booking history is preserved.')
        return redirect('dashboard')
    return render(request, 'marketplace/confirm_delete.html', {
        'kind': 'service', 'item_name': service.title,
        'related_bookings': service.booking_set.count(),
        'live_bookings': live_bookings,
    })


@login_required(login_url='login')
def book_service_view(request, service_id):
    _ensure_role(request, 'customer')
    service = get_object_or_404(Service, pk=service_id, is_active=True)
    form = BookingDateForm(request.POST or None)
    ai_estimate = None
    estimate_error = None
    if request.method == 'POST':
        if request.POST.get('action') == 'estimate':
            try:
                ai_estimate = get_ai_cost_estimate(request.POST.get('problem_description', ''), service)
            except ValueError as exc:
                estimate_error = str(exc)
        elif request.POST.get('action') == 'book' and form.is_valid():
            booking = form.save(commit=False)
            booking.service = service
            booking.customer = request.user
            booking.status = 'Pending'
            booking.save()
            messages.success(request, 'Booking requested! Manage it under My Bookings.')
            return redirect('dashboard')
    return render(request, 'marketplace/book_service.html', {
        'service': service, 'form': form, 'ai_estimate': ai_estimate,
        'estimate_error': estimate_error, 'ai_enabled': bool(configured_provider()),
    })


@login_required(login_url='login')
def edit_booking_view(request, booking_id):
    _ensure_role(request, 'customer')
    booking = get_object_or_404(Booking, pk=booking_id, customer=request.user)
    if booking.status not in ('Pending', 'Accepted'):
        raise PermissionDenied('Only pending or accepted bookings can be changed.')
    form = BookingDateForm(request.POST or None, instance=booking)
    if request.method == 'POST' and form.is_valid():
        was_accepted = booking.status == 'Accepted'
        form.save(commit=False)
        # An accepted booking must be re-approved after the customer changes it.
        if was_accepted:
            booking.status = 'Pending'
        booking.save()
        _notify_booking(booking)
        messages.success(request, 'Booking updated. Provider approval is needed again.' if was_accepted else 'Booking updated successfully.')
        return redirect('dashboard')
    return render(request, 'marketplace/edit_booking.html', {'form': form, 'booking': booking})


@login_required(login_url='login')
def delete_booking_view(request, booking_id):
    _ensure_role(request, 'customer')
    booking = get_object_or_404(Booking, pk=booking_id, customer=request.user)
    if booking.status not in ('Pending', 'Accepted', 'Cancelled'):
        raise PermissionDenied('Completed bookings are kept in your history.')
    if request.method == 'POST':
        booking.delete()
        messages.success(request, 'Booking deleted successfully.')
        return redirect('dashboard')
    return render(request, 'marketplace/confirm_delete.html', {
        'kind': 'booking', 'item_name': booking.service.title, 'booking': booking,
    })


@login_required(login_url='login')
@require_POST
def update_booking_status(request, booking_id, status):
    _ensure_role(request, 'provider')
    booking = get_object_or_404(Booking, pk=booking_id, service__provider=request.user)
    valid_transitions = {'Pending': ('Accepted', 'Cancelled'),
                         'Accepted': ('Completed', 'Cancelled')}
    if status not in valid_transitions.get(booking.status, ()):
        return HttpResponseBadRequest('Invalid booking status transition.')
    booking.status = status
    booking.save(update_fields=['status'])
    _notify_booking(booking)
    messages.success(request, f'Booking marked as {status.lower()}.')
    return redirect('dashboard')


@login_required(login_url='login')
def add_review_view(request, service_id):
    _ensure_role(request, 'customer')
    service = get_object_or_404(Service, pk=service_id)
    if not Booking.objects.filter(customer=request.user, service=service, status='Completed').exists():
        raise PermissionDenied('You can review a service after a completed booking.')
    if request.method == 'POST':
        try:
            rating = int(request.POST.get('rating', '5'))
        except ValueError:
            rating = 0
        comment = request.POST.get('comment', '').strip()
        if 1 <= rating <= 5 and comment:
            Review.objects.create(service=service, customer=request.user, rating=rating, comment=comment)
            messages.success(request, 'Thank you for your review!')
            return redirect('service_detail', service_id=service.pk)
        messages.error(request, 'Select a rating and add your review.')
    return render(request, 'marketplace/add_review.html', {'service': service})


@login_required(login_url='login')
def profile_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user, defaults={'role': 'customer'})
    if request.method == 'POST':
        for field in ('first_name', 'last_name', 'email'):
            setattr(request.user, field, request.POST.get(field, '').strip())
        request.user.save(update_fields=['first_name', 'last_name', 'email'])
        profile.phone_number = request.POST.get('phone_number', '').strip()
        profile.address = request.POST.get('address', '').strip()
        profile.save(update_fields=['phone_number', 'address'])
        messages.success(request, 'Profile saved.')
        return redirect('profile')
    return render(request, 'marketplace/profile.html', {'profile': profile})


def about_view(request):
    return render(request, 'marketplace/about.html')


def service_detail_view(request, service_id):
    service = get_object_or_404(Service.objects.select_related('provider'), pk=service_id)
    return render(request, 'marketplace/service_detail.html', {
        'service': service,
        'reviews': Review.objects.filter(service=service).select_related('customer').order_by('-created_at'),
    })


@login_required(login_url='login')
@require_POST
def ai_chat_api(request):
    if len(request.body) > 12000:
        return JsonResponse({'error': 'Message is too long.'}, status=400)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError('Not an object')
        user_message = data.get('message', '')
        if not isinstance(user_message, str):
            raise ValueError('Message must be text')
        user_message = user_message.strip()
    except (ValueError, TypeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid JSON message.'}, status=400)
    if not 1 <= len(user_message) <= 1500:
        return JsonResponse({'error': 'Message must be 1–1500 characters.'}, status=400)

    role = _role(request)
    booking_count = (Booking.objects.filter(service__provider=request.user).count()
                     if role == 'provider' else Booking.objects.filter(customer=request.user).count())
    service_count = Service.objects.filter(is_active=True).count()
    history = request.session.get('chat_history', [])
    prompt = ('You are ServiGo’s home-service support assistant. Answer in the language of '
              'the user, including Malayalam when appropriate. Be helpful and concise. '
              'Customers can edit/delete their own pending or accepted bookings, but completed '
              'bookings remain in history. When rescheduling an accepted booking, it returns to '
              'Pending for provider approval. Providers can accept or reject pending requests, '
              'mark accepted bookings completed, and edit/delete only their own services. '
              'Do not claim a booking is confirmed, make up a price, or pretend you executed actions. '
              'Refer users to the real service page for prices and estimates.')
    context = f'User role: {role}. Visible booking count: {booking_count}. Available service count: {service_count}.\nQuestion: {user_message}'
    try:
        reply, source = generate_text(prompt, context, history=history)
        mode = 'ai'
    except AIUnavailable:
        reply = fallback_chat_reply(user_message, role, service_count, booking_count,
                                    ai_configured=bool(configured_provider()))
        mode = 'guide'
    history = (history + [{'role': 'user', 'content': user_message},
                          {'role': 'assistant', 'content': reply}])[-6:]
    request.session['chat_history'] = history
    return JsonResponse({'reply': reply, 'mode': mode,
                         'ai_configured': bool(configured_provider())})


@login_required(login_url='login')
@require_POST
def clear_chat_session(request):
    request.session.pop('chat_history', None)
    return JsonResponse({'status': 'cleared'})
