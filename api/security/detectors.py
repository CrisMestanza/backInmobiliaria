from urllib.parse import unquote_plus

from .conf import SecurityConfig, path_matches


def is_allowed_bot(user_agent: str, config: SecurityConfig) -> bool:
    return any(pattern.search(user_agent or "") for pattern in config.whitelist_bot_patterns)


def is_suspicious_user_agent(user_agent: str, config: SecurityConfig) -> bool:
    if is_allowed_bot(user_agent, config):
        return False
    return any(pattern.search(user_agent or "") for pattern in config.suspicious_ua_patterns)


def is_sensitive_path(path: str, config: SecurityConfig) -> bool:
    return path_matches(path, config.sensitive_paths)


def request_is_in_scope(path: str, config: SecurityConfig) -> bool:
    return any((path or "").startswith(prefix) for prefix in config.api_prefixes)


def _small_body_text(request, max_bytes: int) -> str:
    content_type = (request.META.get("CONTENT_TYPE") or "").lower()
    if "multipart/" in content_type:
        return ""
    if not any(kind in content_type for kind in ("json", "x-www-form-urlencoded", "text/plain")):
        return ""
    try:
        content_length = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        return ""
    if content_length <= 0 or content_length > max_bytes:
        return ""
    try:
        return request.body[:max_bytes].decode("utf-8", errors="ignore")
    except Exception:
        return ""


def request_payload_text(request, config: SecurityConfig) -> str:
    query_string = request.META.get("QUERY_STRING") or ""
    pieces = [
        request.path or "",
        unquote_plus(query_string[: config.body_inspection_bytes]),
        _small_body_text(request, config.body_inspection_bytes),
    ]
    return "\n".join(piece for piece in pieces if piece)


def detect_sqli(request, config: SecurityConfig) -> str | None:
    payload = request_payload_text(request, config)
    for pattern in config.sqli_patterns:
        if pattern.search(payload):
            return pattern.pattern
    return None


def detect_path_traversal(request, config: SecurityConfig) -> str | None:
    payload = request_payload_text(request, config)
    for pattern in config.path_traversal_patterns:
        if pattern.search(payload):
            return pattern.pattern
    return None
