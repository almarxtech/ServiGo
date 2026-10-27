from django import forms
from django.contrib.auth.models import User
from django.utils import timezone

from .models import UserProfile, Service, Booking, Complaint, AdvancePayment


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




class ComplaintForm(forms.ModelForm):
    class Meta:
        model = Complaint
        fields = ['booking', 'category', 'subject', 'description']
        widgets = {
            'booking': forms.Select(attrs={'class': 'form-select'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Short summary of your issue'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Describe what happened and what help you need (no passwords or card details)'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        role = getattr(getattr(user, 'userprofile', None), 'role', '') if user else ''
        if role == 'provider':
            bookings = Booking.objects.filter(service__provider=user)
        elif role == 'customer':
            bookings = Booking.objects.filter(customer=user)
        else:
            bookings = Booking.objects.none()
        self.fields['booking'].queryset = bookings.select_related('service').order_by('-created_at')
        self.fields['booking'].required = False
        self.fields['booking'].empty_label = 'General issue (no booking)'

    def clean_subject(self):
        value = self.cleaned_data['subject'].strip()
        if len(value) < 5:
            raise forms.ValidationError('Write a subject of at least 5 characters.')
        return value

    def clean_description(self):
        value = self.cleaned_data['description'].strip()
        if len(value) < 15:
            raise forms.ValidationError('Please describe the issue in at least 15 characters.')
        return value


class AdvancePaymentForm(forms.ModelForm):
    """Customer requests verification of a manual advance, never captures card numbers."""
    class Meta:
        model = AdvancePayment
        fields = ['amount', 'method', 'transaction_reference']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'method': forms.Select(attrs={'class': 'form-select'}),
            'transaction_reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional transfer reference / UTR (no card numbers)', 'autocomplete': 'off'}),
        }
        labels = {'transaction_reference': 'Transfer reference (add once paid)'}

    def __init__(self, *args, booking=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.booking = booking
        if booking:
            self.fields['amount'].widget.attrs['max'] = str(booking.service.price)
            self.fields['amount'].help_text = f'Up to ₹{booking.service.price} (service listed price).'
        self.fields['transaction_reference'].required = False

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise forms.ValidationError('Advance amount must be greater than zero.')
        if self.booking and amount > self.booking.service.price:
            raise forms.ValidationError('Advance cannot exceed the listed service price.')
        return amount

    def clean_transaction_reference(self):
        reference = self.cleaned_data['transaction_reference'].strip()
        if any(x in reference for x in ('\n', '\r')):
            raise forms.ValidationError('Use a single-line transfer reference.')
        return reference
