from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0010_block'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='last_online',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
