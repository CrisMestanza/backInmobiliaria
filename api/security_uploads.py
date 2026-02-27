import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from django.conf import settings
from PIL import Image, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
ALLOWED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png"}


def _sanitize(value):
    text = str(value if value is not None else "na").strip().lower()
    clean = re.sub(r"[^a-z0-9_-]+", "-", text)
    return clean or "na"


def build_secure_image_name(inmobiliaria_id, proyecto_id, image_type, original_name):
    ext = Path(original_name).suffix.lower()
    if ext == ".jpeg":
        ext = ".jpg"
    unique = uuid.uuid4().hex
    inmo = _sanitize(inmobiliaria_id)
    proy = _sanitize(proyecto_id)
    category = _sanitize(image_type)
    return f"inmo_{inmo}/proy_{proy}/{category}_{unique}{ext}"


def _validate_extension(uploaded_file):
    ext = Path(uploaded_file.name).suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError("Formato inválido: solo se permite JPG o PNG.")


def _validate_size(uploaded_file):
    max_size_bytes = int(getattr(settings, "MAX_IMAGE_UPLOAD_MB", 5)) * 1024 * 1024
    if uploaded_file.size > max_size_bytes:
        raise ValidationError(f"Imagen excede tamaño máximo permitido ({settings.MAX_IMAGE_UPLOAD_MB}MB).")


def _validate_mime(uploaded_file):
    content_type = (uploaded_file.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_MIME_TYPES:
        raise ValidationError("MIME inválido: solo image/jpeg o image/png.")


def _validate_real_image(uploaded_file):
    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image.verify()
        uploaded_file.seek(0)
    except (UnidentifiedImageError, OSError):
        raise ValidationError("El archivo no es una imagen válida.")


def _scan_for_malware(uploaded_file):
    if not getattr(settings, "ANTIVIRUS_ENABLED", False):
        return

    scanner_cmd = getattr(settings, "ANTIVIRUS_COMMAND", "clamscan")
    strict = getattr(settings, "ANTIVIRUS_STRICT", False)

    scanner_path = shutil.which(scanner_cmd)
    if not scanner_path:
        if strict:
            raise ValidationError("Antivirus habilitado pero no disponible en servidor.")
        return

    suffix = Path(uploaded_file.name).suffix.lower() or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        uploaded_file.seek(0)
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [scanner_path, "--no-summary", tmp_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
            check=False,
        )
        if result.returncode == 1:
            raise ValidationError("Archivo rechazado por antivirus.")
        if result.returncode not in (0, 1) and strict:
            raise ValidationError("No se pudo validar antivirus en modo estricto.")
    finally:
        uploaded_file.seek(0)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def validate_uploaded_image(uploaded_file):
    _validate_extension(uploaded_file)
    _validate_size(uploaded_file)
    _validate_mime(uploaded_file)
    _validate_real_image(uploaded_file)
    _scan_for_malware(uploaded_file)
