import os

from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand

from api.models import Imagen360
from api.signals import _generate_thumb_360


class Command(BaseCommand):
    help = "Pre-genera thumbnails (2048x1024 JPEG 75%) para todas las imágenes 360 existentes."

    def handle(self, *args, **options):
        imagenes = (
            Imagen360.objects
            .filter(imagen__isnull=False)
            .exclude(imagen="")
            .order_by("id_imagen")
        )
        total = imagenes.count()
        self.stdout.write(f"Imágenes encontradas: {total}")

        generadas = 0
        omitidas = 0
        errores = 0

        for i, img in enumerate(imagenes, 1):
            original_name = img.imagen.name
            root, _ext = os.path.splitext(original_name)
            thumb_name = f"{root}_thumb.jpg"

            if default_storage.exists(thumb_name):
                self.stdout.write(f"  [{i}/{total}] Omitida (ya existe): {thumb_name}")
                omitidas += 1
                continue

            self.stdout.write(f"  [{i}/{total}] Generando thumbnail para id={img.id_imagen}...")
            try:
                _generate_thumb_360(original_name, thumb_name)
                self.stdout.write(self.style.SUCCESS(f"           ✓ OK"))
                generadas += 1
            except Exception as exc:
                self.stdout.write(self.style.ERROR(f"           ✗ Error: {exc}"))
                errores += 1

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Listo: {generadas} generadas, {omitidas} omitidas, {errores} errores."
        ))
