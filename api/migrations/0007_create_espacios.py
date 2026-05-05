from django.db import migrations, models
import django.db.models.deletion


TIPOS_ESPACIO = [
    ("Parque", "parque", "#2e8b57", "park", 10),
    ("Juegos infantiles", "juegos-infantiles", "#f59e0b", "sports_soccer", 20),
    ("Colegio", "colegio", "#facc15", "school", 30),
    ("Iglesia", "iglesia", "#94a3b8", "church", 40),
    ("Supermercado", "supermercado", "#3b82f6", "storefront", 50),
    ("Losa deportiva", "losa-deportiva", "#ef4444", "sports_basketball", 60),
    ("Piscina", "piscina", "#06b6d4", "pool", 70),
    ("Salón comunal", "salon-comunal", "#8b5cf6", "groups", 80),
    ("Área verde", "area-verde", "#22c55e", "grass", 90),
    ("Ciclovía", "ciclovia", "#10b981", "directions_bike", 100),
    ("Seguridad", "seguridad", "#dc2626", "shield", 110),
]


def seed_tipos_espacio(apps, schema_editor):
    TipoEspacio = apps.get_model("api", "TipoEspacio")
    for nombre, slug, color, icono, orden in TIPOS_ESPACIO:
        TipoEspacio.objects.update_or_create(
            slug=slug,
            defaults={
                "nombre": nombre,
                "color": color,
                "icono": icono,
                "orden_visual": orden,
                "estado": 1,
            },
        )


def unseed_tipos_espacio(apps, schema_editor):
    TipoEspacio = apps.get_model("api", "TipoEspacio")
    slugs = [item[1] for item in TIPOS_ESPACIO]
    TipoEspacio.objects.filter(slug__in=slugs).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0006_add_proyecto_financing_config"),
    ]

    operations = [
        migrations.CreateModel(
            name="TipoEspacio",
            fields=[
                ("idtipoespacio", models.AutoField(primary_key=True, serialize=False)),
                ("nombre", models.CharField(max_length=80)),
                ("slug", models.CharField(max_length=80, unique=True)),
                ("color", models.CharField(blank=True, max_length=20, null=True)),
                ("icono", models.CharField(blank=True, max_length=255, null=True)),
                ("orden_visual", models.IntegerField(default=0)),
                ("estado", models.IntegerField(blank=True, default=1, null=True)),
            ],
            options={
                "db_table": "tipo_espacio",
                "managed": True,
            },
        ),
        migrations.CreateModel(
            name="Espacio",
            fields=[
                ("idespacio", models.AutoField(primary_key=True, serialize=False)),
                ("nombre", models.CharField(max_length=120)),
                ("descripcion", models.CharField(blank=True, max_length=500, null=True)),
                ("area_m2", models.DecimalField(blank=True, decimal_places=2, max_digits=14, null=True)),
                ("centro_lat", models.DecimalField(blank=True, decimal_places=8, max_digits=10, null=True)),
                ("centro_lng", models.DecimalField(blank=True, decimal_places=8, max_digits=11, null=True)),
                ("visible_mapa", models.IntegerField(blank=True, default=1, null=True)),
                ("destacado", models.IntegerField(blank=True, default=0, null=True)),
                ("estado", models.IntegerField(blank=True, default=1, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("idproyecto", models.ForeignKey(db_column="idproyecto", on_delete=django.db.models.deletion.CASCADE, related_name="espacios", to="api.proyecto")),
                ("idtipoespacio", models.ForeignKey(db_column="idtipoespacio", on_delete=django.db.models.deletion.PROTECT, related_name="espacios", to="api.tipoespacio")),
            ],
            options={
                "db_table": "espacio",
                "managed": True,
            },
        ),
        migrations.CreateModel(
            name="PuntosEspacio",
            fields=[
                ("idpuntoespacio", models.AutoField(primary_key=True, serialize=False)),
                ("latitud", models.FloatField()),
                ("longitud", models.FloatField()),
                ("orden", models.IntegerField()),
                ("idespacio", models.ForeignKey(db_column="idespacio", on_delete=django.db.models.deletion.CASCADE, related_name="puntos", to="api.espacio")),
            ],
            options={
                "db_table": "puntosespacio",
                "managed": True,
            },
        ),
        migrations.RunPython(seed_tipos_espacio, unseed_tipos_espacio),
    ]
