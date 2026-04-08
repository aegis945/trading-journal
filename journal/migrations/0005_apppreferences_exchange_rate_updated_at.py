from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('journal', '0004_apppreferences'),
    ]

    operations = [
        migrations.AddField(
            model_name='apppreferences',
            name='exchange_rate_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
