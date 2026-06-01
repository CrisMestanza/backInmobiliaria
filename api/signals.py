import io
import logging
import os
import threading

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Imagen360

logger = logging.getLogger(__name__)


def _generate_thumb_360(original_name, thumb_name):
    try:
        from PIL import Image
        with default_storage.open(original_name, 'rb') as f:
            img = Image.open(f)
            img.load()
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.thumbnail((2048, 1024), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=75, optimize=True)
        buf.seek(0)
        default_storage.save(thumb_name, ContentFile(buf.read()))
        logger.info("Thumbnail 360 generado: %s", thumb_name)
    except Exception as exc:
        logger.error("Error generando thumbnail 360 %s: %s", thumb_name, exc)


@receiver(post_save, sender=Imagen360)
def auto_generate_thumbnail(sender, instance, **kwargs):
    if not instance.imagen:
        return
    original_name = instance.imagen.name
    root, _ext = os.path.splitext(original_name)
    thumb_name = f"{root}_thumb.jpg"
    if default_storage.exists(thumb_name):
        return
    t = threading.Thread(target=_generate_thumb_360, args=(original_name, thumb_name), daemon=True)
    t.start()
