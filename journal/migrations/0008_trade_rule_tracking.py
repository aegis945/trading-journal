from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('journal', '0007_make_goal_end_date_optional'),
    ]

    operations = [
        migrations.AddField(
            model_name='trade',
            name='rule_break_notes',
            field=models.TextField(blank=True, help_text='What rule was broken and why?'),
        ),
        migrations.AddField(
            model_name='trade',
            name='rule_break_tags',
            field=models.JSONField(blank=True, default=list, help_text='e.g. ["early entry", "oversized", "revenge trade"]'),
        ),
        migrations.AddField(
            model_name='trade',
            name='rule_review',
            field=models.CharField(blank=True, choices=[('FOLLOWED', 'Followed rules'), ('BROKE', 'Rule break')], help_text='Whether this trade followed your rules or broke them.', max_length=10, null=True),
        ),
    ]
