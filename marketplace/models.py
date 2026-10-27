from django.db import models
from django.contrib.auth.models import User

# USER PROFILE MODEL
class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('customer', 'Customer'),
        ('provider', 'Service Provider'),
    )
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    phone_number = models.CharField(max_length=15)
    address = models.TextField()
    
    def __str__(self):
        return f"{self.user.username} ({self.role})"


# SERVICE MODEL
class Service(models.Model):
    provider = models.ForeignKey(User, on_delete=models.CASCADE, limit_choices_to={'userprofile__role': 'provider'})
    title = models.CharField(max_length=100) # ഉദാഹരണത്തിന്: Pipe Leakage Repair, Deep Cleaning
    description = models.TextField()
    price = models.DecimalField(max_digits=8, decimal_places=2)
    category = models.CharField(max_length=50) # Plumbing, Electrical, Cleaning etc.
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)  # Archived listings keep booking/review history.

    def __str__(self):
        return self.title

# BOOKING MODEL
class Booking(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pending'),
        ('Accepted', 'Accepted'),
        ('Completed', 'Completed'),
        ('Cancelled', 'Cancelled'),
    )

    customer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='customer_bookings', limit_choices_to={'userprofile__role': 'customer'})
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    booking_date = models.DateTimeField()
    problem_description = models.TextField(blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Booking for {self.service.title} by {self.customer.username}"


class Review(models.Model):
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name='reviews')
    customer = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.IntegerField(default=5)  # 1 to 5
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.customer.username} - {self.service.title} ({self.rating}★)"

class Complaint(models.Model):
    """A customer or provider support issue, reviewed only by staff."""
    CATEGORY_CHOICES = (
        ('Booking', 'Booking issue'),
        ('Service', 'Service quality'),
        ('Payment', 'Payment issue'),
        ('Account', 'Account issue'),
        ('Other', 'Other'),
    )
    STATUS_CHOICES = (
        ('Open', 'Open'),
        ('In Review', 'In review'),
        ('Resolved', 'Resolved'),
        ('Dismissed', 'Dismissed'),
    )
    submitted_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='submitted_complaints')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True, related_name='complaints')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    subject = models.CharField(max_length=120)
    description = models.TextField(max_length=2000)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Open')
    admin_response = models.TextField(blank=True, max_length=2000)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_complaints')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'#{self.pk}: {self.subject}'


class AdvancePayment(models.Model):
    """Manual advance-payment request; this does NOT collect or transfer funds."""
    METHOD_CHOICES = (
        ('UPI', 'UPI'),
        ('Bank Transfer', 'Bank transfer'),
        ('Other Transfer', 'Other transfer'),
    )
    STATUS_CHOICES = (
        ('Submitted', 'Submitted — awaiting verification'),
        ('Verified', 'Verified by admin'),
        ('Rejected', 'Rejected'),
    )
    booking = models.OneToOneField(Booking, on_delete=models.PROTECT, related_name='advance_payment')
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    method = models.CharField(max_length=30, choices=METHOD_CHOICES)
    transaction_reference = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Submitted')
    admin_note = models.TextField(max_length=1000, blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_advances')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Advance #{self.pk} for Booking #{self.booking_id} ({self.status})'
