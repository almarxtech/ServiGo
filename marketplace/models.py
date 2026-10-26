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