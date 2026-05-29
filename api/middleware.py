import logging
import time

from api.audit import log_audit_event
from api.error_reporting import notify_backend_exception, notify_backend_response
from api.request_utils import get_client_ip

audit_logger = logging.getLogger("api.audit")


class RequestAuditLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.perf_counter()
        response = None
        status_code = 500
        try:
            response = self.get_response(request)
            status_code = getattr(response, "status_code", 0)
            if response is not None:
                replacement_response = notify_backend_response(request, response)
                if replacement_response is not None:
                    response = replacement_response
                    status_code = getattr(response, "status_code", status_code)
            return response
        except Exception as exc:
            notify_backend_exception(request, exc)
            raise
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            if response is not None:
                status_code = getattr(response, "status_code", status_code)
            audit_logger.info(
                "request_audit method=%s path=%s status=%s ip=%s elapsed_ms=%.2f",
                request.method,
                request.path,
                status_code,
                get_client_ip(request),
                elapsed_ms,
            )
            if str(request.path).startswith("/api/"):
                log_audit_event(
                    request,
                    "http_request",
                    status_code=status_code,
                    success=200 <= int(status_code) < 400,
                    detail={"elapsed_ms": round(elapsed_ms, 2)},
                )


class SecurityHeadersMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.setdefault("X-Permitted-Cross-Domain-Policies", "none")
        if str(request.path).startswith("/api/"):
            response.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
            response.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        return response
