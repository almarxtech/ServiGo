from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('marketplace', '0003_booking_problem_description'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Complaint',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('category', models.CharField(choices=[('Booking', 'Booking issue'), ('Service', 'Service quality'), ('Payment', 'Payment issue'), ('Account', 'Account issue'), ('Other', 'Other')], max_length=20)),
                ('subject', models.CharField(max_length=120)),
                ('description', models.TextField(max_length=2000)),
                ('status', models.CharField(choices=[('Open', 'Open'), ('In Review', 'In review'), ('Resolved', 'Resolved'), ('Dismissed', 'Dismissed')], default='Open', max_length=20)),
                ('admin_response', models.TextField(blank=True, max_length=2000)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('booking', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='complaints', to='marketplace.booking')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_complaints', to=settings.AUTH_USER_MODEL)),
                ('submitted_by', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='submitted_complaints', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
        migrations.CreateModel(
            name='AdvancePayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=8)),
                ('method', models.CharField(choices=[('UPI', 'UPI'), ('Bank Transfer', 'Bank transfer'), ('Other Transfer', 'Other transfer')], max_length=30)),
                ('transaction_reference', models.CharField(blank=True, max_length=120)),
                ('status', models.CharField(choices=[('Submitted', 'Submitted — awaiting verification'), ('Verified', 'Verified by admin'), ('Rejected', 'Rejected')], default='Submitted', max_length=20)),
                ('admin_note', models.TextField(blank=True, max_length=1000)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('booking', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='advance_payment', to='marketplace.booking')),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_advances', to=settings.AUTH_USER_MODEL)),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
