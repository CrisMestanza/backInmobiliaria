from pathlib import Path

from django.conf import settings
from django.core.files.storage import default_storage


def delete_files_and_empty_dirs(paths):
    if not paths:
        return

    media_root = Path(settings.MEDIA_ROOT).resolve()
    touched_dirs = set()

    for raw_path in paths:
        if not raw_path:
            continue

        rel_path = str(raw_path).strip().lstrip("/\\")
        if not rel_path:
            continue

        default_storage.delete(rel_path)
        full_path = (media_root / Path(rel_path)).resolve()
        touched_dirs.add(full_path.parent)

    # Elimina directorios vacios desde el mas profundo hacia arriba.
    for directory in sorted(touched_dirs, key=lambda p: len(p.parts), reverse=True):
        current = directory
        while True:
            try:
                current.relative_to(media_root)
            except ValueError:
                break
            if current == media_root:
                break
            if not current.exists() or not current.is_dir():
                current = current.parent
                continue
            if any(current.iterdir()):
                break
            current.rmdir()
            current = current.parent
