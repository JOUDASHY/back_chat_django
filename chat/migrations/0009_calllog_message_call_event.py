from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0008_message_content_blank'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='call_event',
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='CallLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('room_name', models.CharField(max_length=120, unique=True)),
                ('call_type', models.CharField(choices=[('audio', 'Audio'), ('video', 'Vidéo')], max_length=10)),
                ('status', models.CharField(
                    choices=[
                        ('ringing', 'Sonnerie'),
                        ('completed', 'Terminé'),
                        ('missed', 'Manqué'),
                        ('rejected', 'Refusé'),
                        ('cancelled', 'Annulé'),
                    ],
                    default='ringing',
                    max_length=20,
                )),
                ('started_at', models.DateTimeField(auto_now_add=True)),
                ('answered_at', models.DateTimeField(blank=True, null=True)),
                ('ended_at', models.DateTimeField(blank=True, null=True)),
                ('duration_seconds', models.PositiveIntegerField(default=0)),
                ('caller', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='calls_made',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('recipient', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='calls_received',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('ended_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='calls_ended',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('message', models.OneToOneField(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='call_log',
                    to='chat.message',
                )),
            ],
            options={
                'ordering': ['-started_at'],
            },
        ),
    ]
