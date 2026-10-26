"""REST endpoints with the same ownership rules as the web interface."""
from django.db.models import Q
from rest_framework import permissions, serializers, viewsets
from rest_framework.exceptions import PermissionDenied

from .models import Booking, Review, Service
from .serializers import BookingSerializer, ReviewSerializer, ServiceSerializer


def user_role(user):
    return getattr(getattr(user, 'userprofile', None), 'role', None)


class ServicePermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and user_role(request.user) == 'provider'

    def has_object_permission(self, request, view, obj):
        return request.method in permissions.SAFE_METHODS or obj.provider_id == request.user.pk


class ReviewPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and user_role(request.user) == 'customer'

    def has_object_permission(self, request, view, obj):
        return request.method in permissions.SAFE_METHODS or obj.customer_id == request.user.pk


class ServiceViewSet(viewsets.ModelViewSet):
    queryset = Service.objects.filter(is_active=True).select_related('provider').all()
    serializer_class = ServiceSerializer
    permission_classes = [ServicePermission]

    def perform_create(self, serializer):
        serializer.save(provider=self.request.user)

    def perform_destroy(self, instance):
        if instance.booking_set.filter(status__in=('Pending', 'Accepted')).exists():
            raise PermissionDenied('Resolve active bookings before removing this service.')
        instance.is_active = False
        instance.save(update_fields=['is_active'])


class BookingViewSet(viewsets.ModelViewSet):
    serializer_class = BookingSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Booking.objects.filter(Q(customer=user) | Q(service__provider=user)).distinct().select_related('customer', 'service')

    def perform_create(self, serializer):
        if user_role(self.request.user) != 'customer':
            raise PermissionDenied('Only customers can book a service.')
        serializer.save(customer=self.request.user, status='Pending')

    def perform_destroy(self, instance):
        if instance.customer_id != self.request.user.pk:
            raise PermissionDenied('Providers cannot delete customers’ bookings.')
        if instance.status not in ('Pending', 'Accepted', 'Cancelled'):
            raise PermissionDenied('Completed bookings are retained as history.')
        instance.delete()


class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.select_related('service', 'customer').all()
    serializer_class = ReviewSerializer
    permission_classes = [ReviewPermission]

    def perform_create(self, serializer):
        if not Booking.objects.filter(
            service=serializer.validated_data['service'],
            customer=self.request.user,
            status='Completed',
        ).exists():
            raise PermissionDenied('You can review this service only after a completed booking.')
        serializer.save(customer=self.request.user)
