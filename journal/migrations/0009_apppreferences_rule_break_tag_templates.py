from django.db import migrations, models

import journal.models


class Migration(migrations.Migration):

    dependencies = [
        ('journal', '0008_trade_rule_tracking'),
    ]

    operations = [
        migrations.AddField(
            model_name='apppreferences',
            name='rule_break_tag_templates',
            field=models.JSONField(blank=True, default=journal.models.default_rule_break_tag_templates, help_text='Reusable rule-break tags shown in trade entry forms.'),
        ),
    ]