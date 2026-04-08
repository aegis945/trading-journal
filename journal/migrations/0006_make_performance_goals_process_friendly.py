from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('journal', '0005_apppreferences_exchange_rate_updated_at'),
    ]

    operations = [
        migrations.AlterField(
            model_name='performancegoal',
            name='metric',
            field=models.CharField(blank=True, choices=[('WIN_RATE', 'Win Rate (%)'), ('AVG_RR', 'Avg Risk/Reward'), ('MAX_DRAWDOWN', 'Max Drawdown ($)'), ('TOTAL_PNL', 'Total P&L ($)'), ('TRADE_COUNT', 'Trade Count')], max_length=20, null=True),
        ),
        migrations.AlterField(
            model_name='performancegoal',
            name='target_value',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AlterField(
            model_name='performancegoal',
            name='current_value',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
    ]
