from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0005_add_proyecto_viewer_360_config"),
    ]

    operations = [
        migrations.AddField(
            model_name="proyecto",
            name="financing_config",
            field=models.TextField(blank=True, null=True),
        ),
    ]
