from django.core.cache import cache


OVERVIEW_PREFIX = "dashboard_overview_inmo"
LOTES_PREFIX = "dashboard_lotes_inmo"


def overview_cache_key(idinmobiliaria: int | str) -> str:
    return f"{OVERVIEW_PREFIX}:{idinmobiliaria}"


def lotes_cache_key(idinmobiliaria: int | str, query_string: str) -> str:
    return f"{LOTES_PREFIX}:{idinmobiliaria}:{query_string}"


def lotes_cache_index_key(idinmobiliaria: int | str) -> str:
    return f"{LOTES_PREFIX}:keys:{idinmobiliaria}"


def register_lotes_cache_key(idinmobiliaria: int | str, key: str) -> None:
    index_key = lotes_cache_index_key(idinmobiliaria)
    existing = cache.get(index_key) or []
    if key not in existing:
        existing.append(key)
        cache.set(index_key, existing, timeout=600)


def invalidate_dashboard_cache_for_inmobiliaria(idinmobiliaria: int | str | None) -> None:
    if not idinmobiliaria:
        return
    cache.delete(overview_cache_key(idinmobiliaria))
    index_key = lotes_cache_index_key(idinmobiliaria)
    lotes_keys = cache.get(index_key) or []
    if lotes_keys:
        cache.delete_many(lotes_keys)
    cache.delete(index_key)
