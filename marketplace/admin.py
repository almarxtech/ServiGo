from django.contrib import admin
from .models import AdvancePayment, Booking, Complaint, Review, Service, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'phone_number')
    list_filter = ('role',)
    search_fields = ('user__username',)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('title', 'provider', 'category', 'price', 'is_active')
    list_filter = ('category', 'is_active')
    search_fields = ('title', 'provider__username')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'service', 'customer', 'booking_date', 'status')
    list_filter = ('status',)
    search_fields = ('service__title', 'customer__username')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('service', 'customer', 'rating', 'created_at')
    list_filter = ('rating',)


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('id', 'submitted_by', 'subject', 'category', 'status', 'created_at')
    list_filter = ('category', 'status')
    search_fields = ('submitted_by__username', 'subject', 'description')
    readonly_fields = ('submitted_by', 'booking', 'category', 'subject', 'description',
                       'status', 'admin_response', 'reviewed_by', 'reviewed_at',
                       'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AdvancePayment)
class AdvancePaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'booking', 'amount', 'method', 'status', 'created_at')
    list_filter = ('status', 'method')
    search_fields = ('booking__customer__username', 'transaction_reference')
    readonly_fields = ('booking', 'amount', 'method', 'transaction_reference',
                       'status', 'admin_note', 'reviewed_by', 'reviewed_at',
                       'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
