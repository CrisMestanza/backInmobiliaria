from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name="Usuario",
                    fields=[
                        ("idusuario", models.AutoField(primary_key=True, serialize=False)),
                        ("password", models.CharField(max_length=128)),
                        ("last_login", models.DateTimeField(blank=True, null=True)),
                        ("is_superuser", models.BooleanField(default=False)),
                        ("correo", models.EmailField(max_length=254, unique=True)),
                        ("nombre", models.CharField(blank=True, max_length=60, null=True)),
                        ("estado", models.IntegerField(blank=True, default=1, null=True)),
                        ("is_active", models.BooleanField(default=True)),
                        ("is_staff", models.BooleanField(default=False)),
                    ],
                    options={
                        "db_table": "usuario",
                        "managed": False,
                    },
                )
            ],
        )
    ]
