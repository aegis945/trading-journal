from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('journal', '0003_trade_ta_screenshot'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppPreferences',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('display_currency', models.CharField(choices=[('USD', 'US Dollar ($)'), ('EUR', 'Euro (€)')], default='USD', max_length=3)),
                ('usd_to_eur_rate', models.DecimalField(decimal_places=4, default=Decimal('0.9200'), help_text='Used only when P&L display currency is set to EUR.', max_digits=8, validators=[MinValueValidator(Decimal('0.0001'))], verbose_name='USD to EUR rate')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
