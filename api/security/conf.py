import fnmatch
import ipaddress
import re
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import unquote

from django.conf import settings
from django.core.signals import setting_changed
from django.dispatch import receiver


DEFAULT_WHITELIST_METHODS = ["OPTIONS"]

DEFAULT_WHITELIST_EXACT_PATHS = [
    "/",
    "/api/health/",
    "/api/healthcheck/",
    "/api/healthcheck",
    "/api/security/waf-health/",
    "/health/",
    "/healthcheck/",
    "/favicon.ico",
    "/robots.txt",
]

DEFAULT_WHITELIST_PATH_PREFIXES = [
    "/static/",
    "/media/",
]

DEFAULT_SENSITIVE_PATHS = [
    "/api/schema/swagger-ui",
    "/api/openapi.json",
    "/api/schema",
    "/api/redoc",
    "/api/docs",
    "/api/swagger",
    "/api/graphql/",
    "/api/env",
    "/api/actuator/env",
    "/api/actuator/configprops",
    "/api/actuator/heapdump",
    "/api/heapdump",
    "/api/aws.json",
    "/api/credentials.json",
    "/api/docker-compose.yml",
    "/api/docker-compose.prod.yml",
    "/api/config.json",
    "/api/config.yml",
    "/api/appsettings.json",
    "/api/application.yml",
    "/api/application.properties",
    "/api/database.php",
    "/api/settings.json",
    "/api/settings.yml",
    "/api/secrets.json",
    "/api/keys.json",
    "/api/sonicos/is-sslvpn-enabled",
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
    "/api/v*/appsettings.json",
    "/api/v*/application.yml",
    "/api/v*/application.properties",
    "/api/v*/config.json",
    "/api/v*/config.yml",
    "/api/test",
    "/api/route",
    "/api/credentials",
    "/api/data/*",
    "/api/drf-auth",
    "/api/ping",
    "/api/version",
    "/api/status",
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

DEFAULT_SENSITIVE_SUBSTRINGS = [
    ".env",
    ".git",
    "actuator",
    "heapdump",
    "/env",
    "swagger",
    "swagger-ui",
    "graphql",
    "openapi",
    "phpinfo",
    "docker-compose",
    "credentials",
    "application.yml",
    "application.properties",
    "database.php",
    "secrets.json",
    "keys.json",
    "config",
    "settings",
    "backup",
    "dump.sql",
    "db.sqlite",
    "__pycache__",
    ".bak",
    ".zip",
    ".gz",
    "wp-admin",
    "wp-login",
    "server-status",
    "aws.json",
    "sonicos/is-sslvpn-enabled",
    "sslvpn",
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
    version: str
    whitelist_ips: tuple[str, ...]
    whitelist_bot_patterns: tuple[re.Pattern, ...]
    suspicious_ua_patterns: tuple[re.Pattern, ...]
    sqli_patterns: tuple[re.Pattern, ...]
    path_traversal_patterns: tuple[re.Pattern, ...]
    sensitive_paths: tuple[str, ...]
    sensitive_substrings: tuple[str, ...]
    whitelist_methods: tuple[str, ...]
    whitelist_exact_paths: tuple[str, ...]
    whitelist_path_prefixes: tuple[str, ...]
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
    block_negative_cache_seconds: int
    block_positive_cache_seconds: int
    cleanup_interval_seconds: int
    event_retention_days: int
    max_security_events: int
    cleanup_batch_size: int
    debug_logs: bool


def _compile_many(patterns):
    return tuple(re.compile(pattern) for pattern in patterns)


@lru_cache(maxsize=1)
def get_security_config() -> SecurityConfig:
    raw = getattr(settings, "SECURITY_WAF", {})
    return SecurityConfig(
        enabled=bool(raw.get("ENABLED", True)),
        version=str(raw.get("VERSION", "waf-2026-05-29-response-observer-v2")),
        whitelist_ips=tuple(raw.get("WHITELIST_IPS", ())),
        whitelist_bot_patterns=_compile_many(raw.get("WHITELIST_BOT_UA_PATTERNS", DEFAULT_ALLOWED_BOT_UA_PATTERNS)),
        suspicious_ua_patterns=_compile_many(raw.get("SUSPICIOUS_UA_PATTERNS", DEFAULT_SUSPICIOUS_UA_PATTERNS)),
        sqli_patterns=_compile_many(raw.get("SQLI_PATTERNS", DEFAULT_SQLI_PATTERNS)),
        path_traversal_patterns=_compile_many(raw.get("PATH_TRAVERSAL_PATTERNS", DEFAULT_PATH_TRAVERSAL_PATTERNS)),
        sensitive_paths=tuple(raw.get("SENSITIVE_PATHS", DEFAULT_SENSITIVE_PATHS)),
        sensitive_substrings=tuple(raw.get("SENSITIVE_SUBSTRINGS", DEFAULT_SENSITIVE_SUBSTRINGS)),
        whitelist_methods=tuple(raw.get("WHITELIST_METHODS", DEFAULT_WHITELIST_METHODS)),
        whitelist_exact_paths=tuple(raw.get("WHITELIST_EXACT_PATHS", DEFAULT_WHITELIST_EXACT_PATHS)),
        whitelist_path_prefixes=tuple(raw.get("WHITELIST_PATH_PREFIXES", DEFAULT_WHITELIST_PATH_PREFIXES)),
        api_prefixes=tuple(raw.get("API_PREFIXES", ("/api/",))),
        rate_limit_per_minute=int(raw.get("RATE_LIMIT_PER_MINUTE", 180)),
        burst_limit_per_10_seconds=int(raw.get("BURST_LIMIT_PER_10_SECONDS", 60)),
        concurrent_limit=int(raw.get("CONCURRENT_LIMIT", 12)),
        temp_ban_minutes=int(raw.get("TEMP_BAN_MINUTES", 60)),
        permanent_score=int(raw.get("PERMANENT_SCORE", 200)),
        ban_score=int(raw.get("BAN_SCORE", 100)),
        sensitive_hits_to_ban=int(raw.get("SENSITIVE_HITS_TO_BAN", 3)),
        missing_hits_to_score=int(raw.get("MISSING_HITS_TO_SCORE", 8)),
        body_inspection_bytes=int(raw.get("BODY_INSPECTION_BYTES", 16384)),
        log_sample_seconds=int(raw.get("LOG_SAMPLE_SECONDS", 60)),
        block_negative_cache_seconds=int(raw.get("BLOCK_NEGATIVE_CACHE_SECONDS", 120)),
        block_positive_cache_seconds=int(raw.get("BLOCK_POSITIVE_CACHE_SECONDS", 60)),
        cleanup_interval_seconds=int(raw.get("CLEANUP_INTERVAL_SECONDS", 24 * 3600)),
        event_retention_days=int(raw.get("EVENT_RETENTION_DAYS", 30)),
        max_security_events=int(raw.get("MAX_SECURITY_EVENTS", 50000)),
        cleanup_batch_size=int(raw.get("CLEANUP_BATCH_SIZE", 1000)),
        debug_logs=bool(raw.get("DEBUG_LOGS", False)),
    )


@receiver(setting_changed)
def clear_security_config_cache(setting, **kwargs):
    if setting == "SECURITY_WAF":
        get_security_config.cache_clear()


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
    normalized = unquote(path or "").lower()
    for pattern in patterns:
        candidate = pattern.lower()
        if "*" in candidate:
            if fnmatch.fnmatch(normalized, candidate):
                return True
        elif normalized == candidate or normalized.startswith(candidate.rstrip("/") + "/"):
            return True
    return False


def path_contains_any(path: str, patterns: tuple[str, ...]) -> bool:
    normalized = unquote(path or "").lower()
    return any(pattern.lower() in normalized for pattern in patterns)


def request_path_is_whitelisted(method: str, path: str, config: SecurityConfig) -> bool:
    normalized = unquote(path or "").lower()
    if (method or "").upper() in {item.upper() for item in config.whitelist_methods}:
        return True
    if normalized in {item.lower() for item in config.whitelist_exact_paths}:
        return True
    return any(normalized.startswith(prefix.lower()) for prefix in config.whitelist_path_prefixes)
