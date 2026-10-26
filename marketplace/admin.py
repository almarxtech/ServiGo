from django.contrib import admin
from .models import UserProfile, Service, Booking

admin.site.register(UserProfile)
admin.site.register(Service)
admin.site.register(Booking)