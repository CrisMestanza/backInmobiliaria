from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0003_accountactivationtoken"),
    ]

    operations = [
        migrations.CreateModel(
            name="ApiAuditLog",
            fields=[
                ("idauditlog", models.AutoField(primary_key=True, serialize=False)),
                ("event_type", models.CharField(max_length=80)),
                ("method", models.CharField(blank=True, max_length=10, null=True)),
                ("path", models.CharField(blank=True, max_length=255, null=True)),
                ("status_code", models.IntegerField(blank=True, null=True)),
                ("success", models.BooleanField(default=True)),
                ("ip", models.CharField(blank=True, max_length=80, null=True)),
                ("user_agent", models.CharField(blank=True, max_length=255, null=True)),
                ("actor_email", models.CharField(blank=True, max_length=255, null=True)),
                ("target_resource", models.CharField(blank=True, max_length=80, null=True)),
                ("target_id", models.CharField(blank=True, max_length=80, null=True)),
                ("detail", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "idusuario",
                    models.ForeignKey(
                        blank=True,
                        db_column="idusuario",
                        null=True,
                        on_delete=models.deletion.DO_NOTHING,
                        to="api.usuario",
                    ),
                ),
            ],
            options={
                "db_table": "api_audit_log",
                "managed": True,
            },
        ),
    ]
