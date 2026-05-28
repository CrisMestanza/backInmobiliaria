import hashlib
import logging
from datetime import timedelta

from django.core.cache import cache
from django.db import DatabaseError
from django.utils import timezone

from api.models import BlockedIP, SecurityEvent

logger = logging.getLogger("api.security")


def cache_key(*parts):
    raw = ":".join(str(part) for part in parts)
    return "security:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_incr(key, timeout, amount=1):
    if cache.add(key, 0, timeout=timeout):
        pass
    try:
        return cache.incr(key, amount)
    except ValueError:
        cache.set(key, amount, timeout=timeout)
        return amount


def active_block_for_ip(ip: str):
    key = f"security:block:{ip}"
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        block = BlockedIP.objects.filter(ip_address=ip, is_active=True, expires_at__isnull=True).first()
        if block is None:
            block = (
                BlockedIP.objects.filter(ip_address=ip, is_active=True, expires_at__gt=timezone.now())
                .order_by("-expires_at")
                .first()
            )
        if block:
            ttl = 86400 if block.expires_at is None else max(60, int((block.expires_at - timezone.now()).total_seconds()))
            payload = {"reason": block.reason, "permanent": block.expires_at is None}
            cache.set(key, payload, timeout=ttl)
            return payload
    except DatabaseError:
        logger.exception("blocked_ip_lookup_failed ip=%s", ip)
    cache.set(key, False, timeout=30)
    return False


def clear_block_cache(ip: str):
    cache.delete(f"security:block:{ip}")


def log_security_event(ip, request, event_type, risk_score=0, action="score", reason="", metadata=None, sample_seconds=60):
    fingerprint = cache_key("event", ip, event_type, reason, request.path)
    if action not in {"blocked", "banned"} and not cache.add(fingerprint, True, timeout=sample_seconds):
        return
    try:
        SecurityEvent.objects.create(
            ip_address=ip,
            method=request.method,
            path=(request.get_full_path() or "")[:500],
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:500],
            event_type=event_type,
            risk_score=risk_score,
            action=action,
            reason=reason[:255],
            metadata=metadata or {},
        )
    except Exception:
        logger.exception("security_event_log_failed ip=%s event_type=%s", ip, event_type)


def ban_ip(ip, request, reason, minutes, score, permanent=False, metadata=None):
    now = timezone.now()
    expires_at = None if permanent else now + timedelta(minutes=minutes)
    try:
        block, created = BlockedIP.objects.update_or_create(
            ip_address=ip,
            defaults={
                "reason": reason[:255],
                "risk_score": score,
                "is_active": True,
                "is_permanent": permanent,
                "expires_at": expires_at,
                "last_seen_at": now,
                "user_agent": (request.META.get("HTTP_USER_AGENT") or "")[:500],
                "path": (request.get_full_path() or "")[:500],
            },
        )
        ttl = 86400 if permanent else max(60, int((expires_at - now).total_seconds()))
        cache.set(f"security:block:{ip}", {"reason": block.reason, "permanent": permanent}, timeout=ttl)
        log_security_event(
            ip,
            request,
            "ip_banned",
            risk_score=score,
            action="banned",
            reason=reason,
            metadata=metadata,
            sample_seconds=0,
        )
        return block, created
    except Exception:
        logger.exception("ip_ban_failed ip=%s reason=%s", ip, reason)
        cache.set(f"security:block:{ip}", {"reason": reason, "permanent": permanent}, timeout=300)
        return None, False


def add_risk(ip, request, event_type, points, reason, config, metadata=None):
    score_key = f"security:score:{ip}"
    score = _cache_incr(score_key, timeout=24 * 3600, amount=points)
    log_security_event(
        ip,
        request,
        event_type,
        risk_score=points,
        action="score",
        reason=reason,
        metadata={**(metadata or {}), "score_total": score},
        sample_seconds=config.log_sample_seconds,
    )
    if score >= config.permanent_score:
        ban_ip(ip, request, "risk_score_permanent_threshold", config.temp_ban_minutes, score, permanent=True)
        return score, "banned"
    if score >= config.ban_score:
        ban_ip(ip, request, "risk_score_threshold", config.temp_ban_minutes, score)
        return score, "banned"
    return score, "score"


def add_risk_once(ip, request, event_type, points, reason, config, window_seconds, metadata=None):
    key = cache_key("risk_once", ip, event_type, reason)
    if not cache.add(key, True, timeout=window_seconds):
        return cache.get(f"security:score:{ip}", 0), "counted"
    return add_risk(ip, request, event_type, points, reason, config, metadata)


def rate_limit(ip, request, config):
    minute = _cache_incr(f"security:rate:min:{ip}", timeout=60)
    burst = _cache_incr(f"security:rate:burst:{ip}", timeout=10)
    if minute > config.rate_limit_per_minute:
        score, _ = add_risk(ip, request, "rate_limit_minute", 25, "too_many_requests_per_minute", config)
        return False, 60, score
    if burst > config.burst_limit_per_10_seconds:
        score, _ = add_risk(ip, request, "rate_limit_burst", 20, "request_burst", config)
        return False, 10, score
    return True, None, None


def enter_request(ip, config):
    key = f"security:active:{ip}"
    active = _cache_incr(key, timeout=30)
    return active <= config.concurrent_limit, active


def leave_request(ip):
    key = f"security:active:{ip}"
    try:
        if cache.get(key, 0) > 0:
            cache.decr(key)
    except Exception:
        cache.delete(key)


def record_sensitive_hit(ip, request, config):
    hits = _cache_incr(f"security:sensitive:{ip}", timeout=10 * 60)
    score, action = add_risk(ip, request, "sensitive_path", 35, "sensitive_path_probe", config, {"hits": hits})
    if hits >= config.sensitive_hits_to_ban and action != "banned":
        ban_ip(ip, request, "repeated_sensitive_path_probe", config.temp_ban_minutes, score)
        action = "banned"
    return score, action


def record_missing_path(ip, request, config):
    hits = _cache_incr(f"security:404:{ip}", timeout=10 * 60)
    if hits >= config.missing_hits_to_score:
        return add_risk(ip, request, "not_found_flood", 15, "many_404_responses", config, {"hits": hits})
    return hits, "counted"


def cleanup_expired_blocks():
    updated = BlockedIP.objects.filter(is_active=True, expires_at__isnull=False, expires_at__lte=timezone.now()).update(
        is_active=False
    )
    return updated
