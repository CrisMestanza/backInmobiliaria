from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="PasswordResetCode",
            fields=[
                ("idpasswordreset", models.AutoField(primary_key=True, serialize=False)),
                ("codigo_hash", models.CharField(max_length=255)),
                ("reset_token", models.CharField(blank=True, max_length=120, null=True)),
                ("attempts", models.IntegerField(default=0)),
                ("expires_at", models.DateTimeField()),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("request_ip", models.CharField(blank=True, max_length=80, null=True)),
                (
                    "idusuario",
                    models.ForeignKey(
                        db_column="idusuario",
                        on_delete=models.deletion.DO_NOTHING,
                        related_name="password_reset_codes",
                        to="api.usuario",
                    ),
                ),
            ],
            options={
                "db_table": "password_reset_code",
                "managed": True,
            },
        ),
    ]
