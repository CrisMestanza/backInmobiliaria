import logging

from django.http import JsonResponse

from api.request_utils import get_client_ip

from .conf import get_security_config, ip_is_whitelisted, request_path_is_whitelisted
from .detectors import (
    detect_path_traversal,
    detect_sqli,
    is_sensitive_path,
    is_suspicious_user_agent,
    request_is_in_scope,
)
from .services import (
    active_block_for_ip,
    add_risk,
    add_risk_once,
    ban_ip,
    enter_request,
    leave_request,
    log_security_event,
    maybe_cleanup_security_records,
    rate_limit,
    record_missing_path,
    record_sensitive_hit,
)

logger = logging.getLogger("api.security")


class InternalWAFMiddleware:
    """
    Mini WAF/fail2ban interno para shared hosting.

    El objetivo es bloquear temprano scanners obvios y floods antes de que
    lleguen a DRF/views. Las reglas usan cache primero y DB solo para bans/logs.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        entered_request = False
        view_started = False
        try:
            config = get_security_config()
            if not config.enabled:
                return self.get_response(request)

            ip = get_client_ip(request)
            path = request.path or ""
            user_agent = request.META.get("HTTP_USER_AGENT") or ""
            in_scope = request_is_in_scope(path, config)

            if config.debug_logs:
                print(f"[WAF] {request.method} {path}")
            maybe_cleanup_security_records(config)

            if ip_is_whitelisted(ip, config.whitelist_ips) or request_path_is_whitelisted(request.method, path, config):
                return self.get_response(request)

            block = active_block_for_ip(ip, config)
            if block:
                if config.debug_logs:
                    print(f"[WAF BLOCKED] {ip}")
                log_security_event(
                    ip,
                    request,
                    "blocked_ip_request",
                    risk_score=0,
                    action="blocked",
                    reason=block.get("reason", "blocked_ip"),
                    sample_seconds=config.log_sample_seconds,
                )
                return self._blocked_response(block.get("reason", "blocked_ip"))

            if is_sensitive_path(path, config):
                if config.debug_logs:
                    print(f"[WAF DETECTED] {ip} -> {path}")
                _, action = record_sensitive_hit(ip, request, config)
                if action == "banned":
                    if config.debug_logs:
                        print(f"[WAF BLOCKED] {ip}")
                    return self._blocked_response("repeated_sensitive_path_probe")
                return self._blocked_response("sensitive_path_probe")

            if not in_scope:
                return self.get_response(request)

            allowed_concurrency, active_count = enter_request(ip, config)
            entered_request = True
            if not allowed_concurrency:
                add_risk(
                    ip,
                    request,
                    "concurrent_flood",
                    30,
                    "too_many_concurrent_requests",
                    config,
                    {"active_requests": active_count},
                )
                leave_request(ip)
                entered_request = False
                return self._rate_limited_response(retry_after=10)

            limited, retry_after, score = rate_limit(ip, request, config)
            if not limited:
                leave_request(ip)
                entered_request = False
                return self._rate_limited_response(retry_after=retry_after)

            sqli_pattern = detect_sqli(request, config)
            if sqli_pattern:
                if config.debug_logs:
                    print(f"[WAF DETECTED] {ip} -> {path}")
                ban_ip(
                    ip,
                    request,
                    "sql_injection_payload",
                    config.temp_ban_minutes,
                    score=config.permanent_score,
                    permanent=False,
                    metadata={"pattern": sqli_pattern},
                )
                if config.debug_logs:
                    print(f"[WAF BLOCKED] {ip}")
                leave_request(ip)
                entered_request = False
                return self._blocked_response("sql_injection_payload")

            traversal_pattern = detect_path_traversal(request, config)
            if traversal_pattern:
                if config.debug_logs:
                    print(f"[WAF DETECTED] {ip} -> {path}")
                add_risk(
                    ip,
                    request,
                    "path_traversal_payload",
                    50,
                    "path_traversal_payload",
                    config,
                    {"pattern": traversal_pattern},
                )
                leave_request(ip)
                entered_request = False
                return self._blocked_response("path_traversal_payload")

            if is_suspicious_user_agent(user_agent, config):
                if config.debug_logs:
                    print(f"[WAF DETECTED] {ip} -> {path}")
                score, action = add_risk_once(
                    ip,
                    request,
                    "suspicious_user_agent",
                    15,
                    "suspicious_user_agent",
                    config,
                    10 * 60,
                    {"user_agent": user_agent[:160]},
                )
                if action == "banned":
                    if config.debug_logs:
                        print(f"[WAF BLOCKED] {ip}")
                    leave_request(ip)
                    entered_request = False
                    return self._blocked_response("risk_score_threshold")

            view_started = True
            response = self.get_response(request)
            try:
                if getattr(response, "status_code", None) == 404 and not getattr(
                    request, "_security_response_observed", False
                ):
                    _, action = record_missing_path(ip, request, config)
                    if action == "banned":
                        if config.debug_logs:
                            print(f"[WAF BLOCKED] {ip}")
                        return self._blocked_response("many_404_responses")
            except Exception:
                logger.exception("internal_waf_response_observer_failed path=%s", getattr(request, "path", ""))
            return response
        except Exception:
            if view_started:
                raise
            logger.exception("internal_waf_failed path=%s", getattr(request, "path", ""))
            return self.get_response(request)
        finally:
            if entered_request:
                leave_request(ip)

    @staticmethod
    def _blocked_response(reason, status=403):
        return JsonResponse(
            {"detail": "Request blocked.", "code": "security_blocked"},
            status=status,
            headers={"X-Security-Block": str(reason)},
        )

    @staticmethod
    def _rate_limited_response(retry_after=60):
        return JsonResponse(
            {"detail": "Too many requests.", "code": "rate_limited"},
            status=429,
            headers={"Retry-After": str(retry_after), "X-Security-Block": "rate_limit"},
        )
