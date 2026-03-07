import logging
import time

from api.audit import log_audit_event
from api.request_utils import get_client_ip

audit_logger = logging.getLogger("api.audit")


class RequestAuditLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        started = time.perf_counter()
        response = self.get_response(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        status_code = getattr(response, "status_code", 0)
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
        return response
