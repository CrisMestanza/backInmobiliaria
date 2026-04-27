from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0004_apiauditlog"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE proyecto
                ADD COLUMN viewer_360_config LONGTEXT NULL;
            """,
            reverse_sql="""
                ALTER TABLE proyecto
                DROP COLUMN viewer_360_config;
            """,
        ),
    ]
