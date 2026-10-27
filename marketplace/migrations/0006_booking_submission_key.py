# Preserve existing bookings while preventing duplicate booking form submissions.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0005_advancepayment_gateway_method_and_more')]

    operations = [
        migrations.AddField(
            model_name='booking',
            name='submission_key',
            field=models.UUIDField(blank=True, editable=False, null=True, unique=True),
        ),
    ]
