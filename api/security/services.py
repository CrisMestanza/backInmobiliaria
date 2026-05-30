import hashlib
import logging
from datetime import timedelta

from django.core.cache import cache
from django.db import DatabaseError
from django.utils import timezone

from api.models import BlockedIP, SecurityEvent
from api.request_utils import get_client_ip

from .conf import get_security_config, ip_is_whitelisted, request_path_is_whitelisted
from .detectors import is_sensitive_path

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


def active_block_for_ip(ip: str, config=None):
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
            positive_ttl = getattr(config, "block_positive_cache_seconds", 60)
            ttl = min(ttl, positive_ttl) if positive_ttl and positive_ttl > 0 else ttl
            payload = {"reason": block.reason, "permanent": block.expires_at is None}
            cache.set(key, payload, timeout=ttl)
            return payload
    except DatabaseError:
        logger.exception("blocked_ip_lookup_failed ip=%s", ip)
    negative_ttl = getattr(config, "block_negative_cache_seconds", 120)
    cache.set(key, False, timeout=negative_ttl)
    return False


def clear_block_cache(ip: str):
    cache.delete(f"security:block:{ip}")


def log_security_event(ip, request, event_type, risk_score=0, action="score", reason="", metadata=None, sample_seconds=60):
    fingerprint = cache_key("event", ip, event_type, reason, request.path)
    should_sample = sample_seconds and sample_seconds > 0 and action != "banned"
    if should_sample and not cache.add(fingerprint, True, timeout=sample_seconds):
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
        config = get_security_config()
        positive_ttl = getattr(config, "block_positive_cache_seconds", 60)
        ttl = min(ttl, positive_ttl) if positive_ttl and positive_ttl > 0 else ttl
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


def add_risk(ip, request, event_type, points, reason, config, metadata=None, ban_reason=None):
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
        ban_ip(ip, request, ban_reason or "risk_score_permanent_threshold", config.temp_ban_minutes, score, permanent=True)
        return score, "banned"
    if score >= config.ban_score:
        ban_ip(ip, request, ban_reason or "risk_score_threshold", config.temp_ban_minutes, score)
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
        score, _ = add_risk(ip, request, "rate_limit_minute", 40, "too_many_requests_per_minute", config)
        return False, 60, score
    if burst > config.burst_limit_per_10_seconds:
        score, _ = add_risk(ip, request, "rate_limit_burst", 40, "request_burst", config)
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
    score, action = add_risk(ip, request, "sensitive_path", 30, "sensitive_path_probe", config, {"hits": hits})
    if hits >= config.sensitive_hits_to_ban and action != "banned":
        score, action = add_risk(
            ip,
            request,
            "repeated_scanner_requests",
            20,
            "repeated_sensitive_path_probe",
            config,
            {"hits": hits},
            ban_reason="repeated_sensitive_path_probe",
        )
    if hits >= config.sensitive_hits_to_ban and action != "banned":
        ban_ip(ip, request, "repeated_sensitive_path_probe", config.temp_ban_minutes, score)
        action = "banned"
    return score, action


def record_missing_path(ip, request, config):
    hits = _cache_incr(f"security:404:{ip}", timeout=10 * 60)
    if hits >= config.missing_hits_to_score:
        return add_risk(ip, request, "not_found_flood", 20, "many_404_responses", config, {"hits": hits})
    return hits, "counted"


def _attach_security_observation(
    request,
    *,
    event_type,
    reason,
    risk_delta=0,
    score_total=None,
    action="counted",
    hits=None,
    status_code=None,
    blocked=False,
):
    request._security_observation = {
        "event_type": event_type,
        "reason": reason,
        "risk_delta": risk_delta,
        "score_total": score_total,
        "action": action,
        "hits": hits,
        "status_code": status_code,
        "blocked": blocked,
    }


def observe_security_response(request, response):
    """
    Segunda capa: alimenta el score del WAF desde respuestas 404/403/500.

    Corre despues de las views, por eso no intenta cambiar la respuesta actual.
    Si supera el threshold, crea BlockedIP y el siguiente request se corta en el
    middleware antes de DRF/views.
    """
    config = get_security_config()
    if not config.enabled:
        return None
    request._security_response_observed = True

    path = request.path or ""
    status_code = int(getattr(response, "status_code", 0) or 0)
    if status_code not in {403, 404, 500} and status_code < 500:
        return None
    if request_path_is_whitelisted(request.method, path, config):
        return None

    ip = get_client_ip(request)
    path_is_sensitive = is_sensitive_path(path, config)

    if path_is_sensitive:
        hits = _cache_incr(f"security:response_sensitive:{ip}", timeout=10 * 60)
        score, action = add_risk(
            ip,
            request,
            "sensitive_response_path",
            30,
            "sensitive_path_after_response",
            config,
            {"hits": hits, "status_code": status_code, "source": "response_observer"},
            ban_reason="repeated_sensitive_path_probe",
        )
        _attach_security_observation(
            request,
            event_type="sensitive_response_path",
            reason="sensitive_path_after_response",
            risk_delta=30,
            score_total=score,
            action=action,
            hits=hits,
            status_code=status_code,
            blocked=action == "banned",
        )
        if hits >= config.sensitive_hits_to_ban and action != "banned":
            score, action = add_risk(
                ip,
                request,
                "repeated_scanner_response",
                20,
                "repeated_sensitive_path_probe",
                config,
                {"hits": hits, "status_code": status_code, "source": "response_observer"},
                ban_reason="repeated_sensitive_path_probe",
            )
            _attach_security_observation(
                request,
                event_type="repeated_scanner_response",
                reason="repeated_sensitive_path_probe",
                risk_delta=20,
                score_total=score,
                action=action,
                hits=hits,
                status_code=status_code,
                blocked=action == "banned",
            )
        if hits >= config.sensitive_hits_to_ban and action != "banned":
            ban_ip(ip, request, "repeated_sensitive_path_probe", config.temp_ban_minutes, score)
            action = "banned"
            _attach_security_observation(
                request,
                event_type="ip_banned",
                reason="repeated_sensitive_path_probe",
                risk_delta=0,
                score_total=score,
                action=action,
                hits=hits,
                status_code=status_code,
                blocked=True,
            )
        return action

    if ip_is_whitelisted(ip, config.whitelist_ips):
        return None

    if status_code == 404:
        hits_or_score, action = record_missing_path(ip, request, config)
        _attach_security_observation(
            request,
            event_type="not_found_flood" if action in {"score", "banned"} else "not_found",
            reason="many_404_responses" if action in {"score", "banned"} else "not_found_counted",
            risk_delta=20 if action in {"score", "banned"} else 0,
            score_total=hits_or_score if action in {"score", "banned"} else cache.get(f"security:score:{ip}", 0),
            action=action,
            hits=hits_or_score if action == "counted" else None,
            status_code=status_code,
            blocked=action == "banned",
        )
        return action

    if status_code >= 500:
        score, action = add_risk_once(
            ip,
            request,
            "server_error_response",
            10,
            "server_error_response",
            config,
            5 * 60,
            {"status_code": status_code, "source": "response_observer"},
        )
        _attach_security_observation(
            request,
            event_type="server_error_response",
            reason="server_error_response",
            risk_delta=10 if action != "counted" else 0,
            score_total=score,
            action=action,
            status_code=status_code,
            blocked=action == "banned",
        )
        return action

    return None


def cleanup_expired_blocks():
    updated = BlockedIP.objects.filter(is_active=True, expires_at__isnull=False, expires_at__lte=timezone.now()).update(
        is_active=False
    )
    return updated


def cleanup_security_records(config=None):
    config = config or get_security_config()
    expired_blocks = cleanup_expired_blocks()
    cutoff = timezone.now() - timedelta(days=config.event_retention_days)
    old_events_deleted, _ = SecurityEvent.objects.filter(created_at__lt=cutoff).delete()

    capped_events_deleted = 0
    max_events = max(0, int(config.max_security_events))
    if max_events:
        overflow = SecurityEvent.objects.count() - max_events
        if overflow > 0:
            delete_count = min(overflow, max(1, int(config.cleanup_batch_size)))
            ids = list(
                SecurityEvent.objects.order_by("created_at")
                .values_list("idsecurityevent", flat=True)[:delete_count]
            )
            if ids:
                capped_events_deleted, _ = SecurityEvent.objects.filter(idsecurityevent__in=ids).delete()

    return {
        "expired_blocks": expired_blocks,
        "old_events_deleted": old_events_deleted,
        "capped_events_deleted": capped_events_deleted,
    }


def maybe_cleanup_security_records(config=None):
    config = config or get_security_config()
    if config.cleanup_interval_seconds <= 0:
        return None
    if not cache.add("security:cleanup:lock", True, timeout=config.cleanup_interval_seconds):
        return None
    try:
        return cleanup_security_records(config)
    except Exception:
        logger.exception("security_cleanup_failed")
        return None
