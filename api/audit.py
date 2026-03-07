import json

from api.models import ApiAuditLog
from api.request_utils import get_client_ip


def _safe_detail(detail):
    if detail is None:
        return None
    if isinstance(detail, str):
        return detail[:2000]
    try:
        return json.dumps(detail, ensure_ascii=False)[:2000]
    except Exception:
        return str(detail)[:2000]


def log_audit_event(
    request,
    event_type,
    *,
    status_code=None,
    success=True,
    target_resource=None,
    target_id=None,
    detail=None,
):
    try:
        user = getattr(request, "user", None)
        user_id = getattr(user, "idusuario", None) if user and getattr(user, "is_authenticated", False) else None
        actor_email = getattr(user, "correo", None) if user_id else None
        ApiAuditLog.objects.create(
            event_type=event_type,
            method=getattr(request, "method", None),
            path=getattr(request, "path", None),
            status_code=status_code,
            success=bool(success),
            ip=get_client_ip(request),
            user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:255],
            idusuario_id=user_id,
            actor_email=actor_email,
            target_resource=target_resource,
            target_id=str(target_id) if target_id is not None else None,
            detail=_safe_detail(detail),
        )
    except Exception:
        # Nunca bloquear flujo principal por errores de auditoría
        return
