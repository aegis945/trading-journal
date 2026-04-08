from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('journal', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tradingsession',
            name='market_bias',
            field=models.CharField(blank=True, choices=[('BULLISH', 'Bullish'), ('BEARISH', 'Bearish'), ('NEUTRAL', 'Neutral')], max_length=10, null=True),
        ),
        migrations.AlterField(
            model_name='tradingsession',
            name='psychological_state',
            field=models.IntegerField(blank=True, help_text='1 (worst) – 5 (best) mental state before trading', null=True),
        ),
    ]