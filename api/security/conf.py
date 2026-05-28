import fnmatch
import ipaddress
import re
from dataclasses import dataclass

from django.conf import settings


DEFAULT_SENSITIVE_PATHS = [
    "/api/schema/swagger-ui",
    "/api/openapi.json",
    "/api/schema",
    "/api/redoc",
    "/api/docs",
    "/api/swagger",
    "/api/graphql/",
    "/api/dump.sql",
    "/api/db.sqlite3",
    "/api/__pycache__/*",
    "/api/.env",
    "/api/.env.*",
    "/api/.env/public/.env",
    "/api/settings",
    "/api/settings.py",
    "/api/phpinfo.php",
    "/api/config",
    "/api/config.env",
    "/api/config.js",
    "/api/login.php",
    "/api/index.php",
    "/api/proxy",
    "/api/v*/proxy",
    "/api/serverless/*",
    "/api/webhook/*",
    "/api/users/*",
    "/api/auth/*",
    "/api/public/storeinfo",
    "/api/v1/guest/comm/config",
    "/api/v1/workflows",
    "/api/v1/executions",
    "/api/v1/credentials",
    "/api/shared/config.env",
    "/api/shared/config/config.env",
    "/api/staging/.env",
    "/api/v*/.env",
    "/api/test",
    "/api/route",
    "/api/credentials",
    "/api/data/*",
    "/api/drf-auth",
    "/api/ping",
    "/api/version",
    "/api/status",
    "/api/healthcheck",
    "/api/*.php",
    "/api/*.php.*",
    "/api/objects/*.php*",
    "/.env",
    "/.git/*",
    "/wp-admin/*",
    "/wp-login.php",
    "/xmlrpc.php",
    "/vendor/*",
    "/phpmyadmin/*",
]

DEFAULT_SQLI_PATTERNS = [
    r"(?i)(?:^|[^\w])or\s+1\s*=\s*1(?:[^\w]|$)",
    r"(?i)(?:^|[^\w])or\s+['\"]?1['\"]?\s*=\s*['\"]?1['\"]?(?:[^\w]|$)",
    r"(?i)union\s+(?:all\s+)?select\b",
    r"(?i)(?:sleep|benchmark)\s*\(",
    r"(?i)information_schema",
    r"(?i)(?:--|#|/\*)\s*$",
    r"(?i)\b(?:drop|alter|truncate)\s+table\b",
]

DEFAULT_PATH_TRAVERSAL_PATTERNS = [
    r"(?i)(?:\.\./|\.\.\\|%2e%2e%2f|%2e%2e%5c)",
    r"(?i)(?:/etc/passwd|/proc/self|boot\.ini|win\.ini)",
]

DEFAULT_SUSPICIOUS_UA_PATTERNS = [
    r"(?i)\b(sqlmap|acunetix|nikto|nmap|masscan|zgrab|wpscan|dirbuster|gobuster|ffuf|hydra)\b",
    r"(?i)\b(python-requests|curl|wget|httpclient|libwww-perl|java/|go-http-client)\b",
    r"(?i)^\s*$",
]

DEFAULT_ALLOWED_BOT_UA_PATTERNS = [
    r"(?i)googlebot",
    r"(?i)bingbot",
    r"(?i)duckduckbot",
    r"(?i)yandexbot",
    r"(?i)baiduspider",
    r"(?i)facebookexternalhit",
    r"(?i)twitterbot",
    r"(?i)linkedinbot",
    r"(?i)whatsapp",
]


@dataclass(frozen=True)
class SecurityConfig:
    enabled: bool
    whitelist_ips: tuple[str, ...]
    whitelist_bot_patterns: tuple[re.Pattern, ...]
    suspicious_ua_patterns: tuple[re.Pattern, ...]
    sqli_patterns: tuple[re.Pattern, ...]
    path_traversal_patterns: tuple[re.Pattern, ...]
    sensitive_paths: tuple[str, ...]
    api_prefixes: tuple[str, ...]
    rate_limit_per_minute: int
    burst_limit_per_10_seconds: int
    concurrent_limit: int
    temp_ban_minutes: int
    permanent_score: int
    ban_score: int
    sensitive_hits_to_ban: int
    missing_hits_to_score: int
    body_inspection_bytes: int
    log_sample_seconds: int


def _compile_many(patterns):
    return tuple(re.compile(pattern) for pattern in patterns)


def get_security_config() -> SecurityConfig:
    raw = getattr(settings, "SECURITY_WAF", {})
    return SecurityConfig(
        enabled=bool(raw.get("ENABLED", True)),
        whitelist_ips=tuple(raw.get("WHITELIST_IPS", ())),
        whitelist_bot_patterns=_compile_many(raw.get("WHITELIST_BOT_UA_PATTERNS", DEFAULT_ALLOWED_BOT_UA_PATTERNS)),
        suspicious_ua_patterns=_compile_many(raw.get("SUSPICIOUS_UA_PATTERNS", DEFAULT_SUSPICIOUS_UA_PATTERNS)),
        sqli_patterns=_compile_many(raw.get("SQLI_PATTERNS", DEFAULT_SQLI_PATTERNS)),
        path_traversal_patterns=_compile_many(raw.get("PATH_TRAVERSAL_PATTERNS", DEFAULT_PATH_TRAVERSAL_PATTERNS)),
        sensitive_paths=tuple(raw.get("SENSITIVE_PATHS", DEFAULT_SENSITIVE_PATHS)),
        api_prefixes=tuple(raw.get("API_PREFIXES", ("/api/",))),
        rate_limit_per_minute=int(raw.get("RATE_LIMIT_PER_MINUTE", 180)),
        burst_limit_per_10_seconds=int(raw.get("BURST_LIMIT_PER_10_SECONDS", 60)),
        concurrent_limit=int(raw.get("CONCURRENT_LIMIT", 12)),
        temp_ban_minutes=int(raw.get("TEMP_BAN_MINUTES", 60)),
        permanent_score=int(raw.get("PERMANENT_SCORE", 140)),
        ban_score=int(raw.get("BAN_SCORE", 70)),
        sensitive_hits_to_ban=int(raw.get("SENSITIVE_HITS_TO_BAN", 3)),
        missing_hits_to_score=int(raw.get("MISSING_HITS_TO_SCORE", 8)),
        body_inspection_bytes=int(raw.get("BODY_INSPECTION_BYTES", 16384)),
        log_sample_seconds=int(raw.get("LOG_SAMPLE_SECONDS", 60)),
    )


def ip_is_whitelisted(ip: str, networks: tuple[str, ...]) -> bool:
    if not ip:
        return False
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ip in networks
    for item in networks:
        try:
            if address in ipaddress.ip_network(item, strict=False):
                return True
        except ValueError:
            if ip == item:
                return True
    return False


def path_matches(path: str, patterns: tuple[str, ...]) -> bool:
    normalized = (path or "").lower()
    for pattern in patterns:
        candidate = pattern.lower()
        if "*" in candidate:
            if fnmatch.fnmatch(normalized, candidate):
                return True
        elif normalized == candidate or normalized.startswith(candidate.rstrip("/") + "/"):
            return True
    return False
