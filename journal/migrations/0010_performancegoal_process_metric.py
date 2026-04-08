from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('journal', '0009_apppreferences_rule_break_tag_templates'),
    ]

    operations = [
        migrations.AddField(
            model_name='performancegoal',
            name='process_metric',
            field=models.CharField(blank=True, choices=[('PROCESS_SCORE', 'Overall Process Score (%)'), ('FOLLOW_RULES', 'Follow Rules (%)'), ('SESSION_PREP', 'Session Prep Completion (%)'), ('SESSION_REVIEW', 'Session Review Completion (%)')], max_length=20, null=True),
        ),
    ]