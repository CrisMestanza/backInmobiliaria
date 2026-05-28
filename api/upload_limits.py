from django.conf import settings
from rest_framework.exceptions import ValidationError


def enforce_file_batch_limits(files, *, max_files_setting, max_total_mb_setting, default_max_files, default_total_mb):
    max_files = int(getattr(settings, max_files_setting, default_max_files))
    max_total_bytes = int(getattr(settings, max_total_mb_setting, default_total_mb)) * 1024 * 1024
    file_list = list(files or [])
    if len(file_list) > max_files:
        raise ValidationError(f"Demasiados archivos. Maximo permitido: {max_files}.")
    total_size = sum(int(getattr(file_obj, "size", 0) or 0) for file_obj in file_list)
    if total_size > max_total_bytes:
        raise ValidationError(f"El total de archivos excede {max_total_bytes // (1024 * 1024)}MB.")
    return file_list
