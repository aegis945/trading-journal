from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('journal', '0002_alter_tradingsession_empty_defaults'),
    ]

    operations = [
        migrations.AddField(
            model_name='trade',
            name='ta_screenshot',
            field=models.ImageField(blank=True, help_text='Optional technical analysis screenshot for this trade', null=True, upload_to='trade_ta/'),
        ),
    ]