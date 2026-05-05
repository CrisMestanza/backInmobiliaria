from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0005_add_proyecto_viewer_360_config"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="""
                        ALTER TABLE proyecto
                        ADD COLUMN financing_config LONGTEXT NULL;
                    """,
                    reverse_sql="""
                        ALTER TABLE proyecto
                        DROP COLUMN financing_config;
                    """,
                ),
            ],
            state_operations=[
                migrations.CreateModel(
                    name="Proyecto",
                    fields=[
                        ("idproyecto", models.AutoField(primary_key=True, serialize=False)),
                        ("viewer_360_config", models.TextField(blank=True, null=True)),
                        ("financing_config", models.TextField(blank=True, null=True)),
                    ],
                    options={
                        "db_table": "proyecto",
                        "managed": False,
                    },
                ),
            ],
        ),
    ]
