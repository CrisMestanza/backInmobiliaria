from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0002_passwordresetcode"),
    ]

    operations = [
        migrations.CreateModel(
            name="AccountActivationToken",
            fields=[
                ("idactivationtoken", models.AutoField(primary_key=True, serialize=False)),
                ("token_hash", models.CharField(max_length=128, unique=True)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("request_ip", models.CharField(blank=True, max_length=80, null=True)),
                (
                    "idusuario",
                    models.ForeignKey(
                        db_column="idusuario",
                        on_delete=models.deletion.DO_NOTHING,
                        related_name="activation_tokens",
                        to="api.usuario",
                    ),
                ),
            ],
            options={
                "db_table": "account_activation_token",
                "managed": True,
            },
        ),
    ]
