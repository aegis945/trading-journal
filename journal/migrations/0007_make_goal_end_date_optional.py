from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('journal', '0006_make_performance_goals_process_friendly'),
    ]

    operations = [
        migrations.AlterField(
            model_name='performancegoal',
            name='end_date',
            field=models.DateField(blank=True, null=True),
        ),
    ]
