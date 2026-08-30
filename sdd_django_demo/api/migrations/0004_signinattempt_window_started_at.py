from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0001_signinattempt'),
        ('api', '0002_passwordresetcode_one_usable_reset_code_per_user'),
    ]

    operations = [
        migrations.AddField(
            model_name='signinattempt',
            name='window_started_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
