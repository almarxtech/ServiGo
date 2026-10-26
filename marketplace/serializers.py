from django.utils import timezone
from rest_framework import serializers

from .models import Booking, Review, Service


class ReviewSerializer(serializers.ModelSerializer):
    customer = serializers.ReadOnlyField(source='customer.username')

    class Meta:
        model = Review
        fields = ['id', 'service', 'customer', 'rating', 'comment', 'created_at']
        read_only_fields = ['id', 'customer', 'created_at']

    def validate_rating(self, rating):
        if not 1 <= rating <= 5:
            raise serializers.ValidationError('Rating must be between 1 and 5.')
        return rating

    def validate(self, attrs):
        if self.instance and 'service' in attrs and attrs['service'] != self.instance.service:
            raise serializers.ValidationError({'service': 'You cannot change the reviewed service.'})
        return attrs


class ServiceSerializer(serializers.ModelSerializer):
    provider = serializers.ReadOnlyField(source='provider.username')

    class Meta:
        model = Service
        fields = ['id', 'provider', 'title', 'description', 'price', 'category', 'created_at']
        read_only_fields = ['id', 'provider', 'created_at']

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError('Price must be greater than zero.')
        return value


class BookingSerializer(serializers.ModelSerializer):
    customer = serializers.ReadOnlyField(source='customer.username')
    service_title = serializers.ReadOnlyField(source='service.title')

    class Meta:
        model = Booking
        fields = ['id', 'service', 'service_title', 'customer', 'booking_date',
                  'problem_description', 'status', 'created_at']
        read_only_fields = ['id', 'service_title', 'customer', 'created_at']

    def validate(self, attrs):
        user = self.context['request'].user
        if not self.instance and attrs.get('service') and not attrs['service'].is_active:
            raise serializers.ValidationError({'service': 'This service is no longer available.'})
        if self.instance:
            booking = self.instance
            if 'service' in attrs and attrs['service'] != booking.service:
                raise serializers.ValidationError({'service': 'The service for a booking cannot be changed.'})
            is_provider = booking.service.provider_id == user.pk
            if is_provider:
                if 'booking_date' in attrs or 'problem_description' in attrs:
                    raise serializers.ValidationError('Providers cannot edit customers’ booking details.')
                valid_transitions = {'Pending': ('Accepted', 'Cancelled'),
                                     'Accepted': ('Completed', 'Cancelled')}
                new_status = attrs.get('status')
                if new_status not in valid_transitions.get(booking.status, ()):
                    raise serializers.ValidationError({'status': 'Invalid status transition.'})
            else:
                if booking.customer_id != user.pk:
                    raise serializers.ValidationError('You cannot modify this booking.')
                if booking.status not in ('Pending', 'Accepted'):
                    raise serializers.ValidationError('Only pending or accepted bookings can be edited.')
                if 'status' in attrs and attrs['status'] != booking.status:
                    raise serializers.ValidationError({'status': 'Only the provider can update status.'})
                if not ({'booking_date', 'problem_description'} & attrs.keys()):
                    raise serializers.ValidationError('Provide updated booking details.')
                if booking.status == 'Accepted':
                    attrs['status'] = 'Pending'
        else:
            if 'status' in attrs and attrs['status'] != 'Pending':
                raise serializers.ValidationError({'status': 'New bookings must be pending.'})
        if 'booking_date' in attrs and attrs['booking_date'] <= timezone.now():
            raise serializers.ValidationError({'booking_date': 'Please select a future date and time.'})
        if not self.instance and 'booking_date' not in attrs:
            raise serializers.ValidationError({'booking_date': 'Appointment date is required.'})
        return attrs
