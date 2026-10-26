from django import forms
from django.contrib.auth.models import User
from django.utils import timezone

from .models import UserProfile, Service, Booking


class UserRegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Create a password'}))
    role = forms.ChoiceField(choices=UserProfile.ROLE_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    phone_number = forms.CharField(max_length=15, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your phone number'}))
    address = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Your address'}))

    class Meta:
        model = User
        fields = ['username', 'email', 'password']
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Choose a username'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'you@example.com'}),
        }


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = ['title', 'description', 'price', 'category']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Expert plumbing repair'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Describe what is included in this service...'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'min': '0.01', 'step': '0.01', 'placeholder': 'e.g. 750.00'}),
            'category': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Plumbing, Cleaning, Electrical'}),
        }

    def clean_price(self):
        price = self.cleaned_data['price']
        if price <= 0:
            raise forms.ValidationError('Price must be greater than zero.')
        return price


class BookingDateForm(forms.ModelForm):
    booking_date = forms.DateTimeField(
        input_formats=['%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S'],
        widget=forms.DateTimeInput(
            format='%Y-%m-%dT%H:%M',
            attrs={'type': 'datetime-local', 'class': 'form-control', 'step': '60'},
        ),
        label='Preferred date & time',
    )

    problem_description = forms.CharField(
        required=False, max_length=1500, label='Describe the work (optional)',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4,
                                    'placeholder': 'e.g. Kitchen sink leaking under the tap; water is collecting on the floor...'}),
    )

    class Meta:
        model = Booking
        fields = ['booking_date', 'problem_description']

    def clean_booking_date(self):
        booking_date = self.cleaned_data['booking_date']
        if booking_date <= timezone.now():
            raise forms.ValidationError('Please select a future date and time.')
        return booking_date


