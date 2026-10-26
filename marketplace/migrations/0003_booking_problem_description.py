from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0002_review')]
    operations = [migrations.AddField(model_name='booking', name='problem_description',
                                      field=models.TextField(blank=True, default='')),
                  migrations.AddField(model_name='service', name='is_active',
                                      field=models.BooleanField(default=True))]
