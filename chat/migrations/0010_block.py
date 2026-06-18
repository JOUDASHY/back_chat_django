from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0009_calllog_message_call_event'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Block',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('blocker', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='blocking',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('blocked', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='blocked_by',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['-created_at'],
                'unique_together': {('blocker', 'blocked')},
            },
        ),
    ]
