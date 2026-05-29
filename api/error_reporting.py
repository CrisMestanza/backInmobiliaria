import json
import logging
import traceback
from datetime import datetime
from email.utils import format_datetime
from html import escape

import requests
from django.conf import settings
from django.http import JsonResponse
from django.http.request import RawPostDataException

from api.request_utils import get_client_ip
from api.security.conf import get_security_config
from api.security.services import observe_security_response

logger = logging.getLogger("api.error_reporting")

SENSITIVE_KEY_TOKENS = (
    "password",
    "token",
    "authorization",
    "cookie",
    "secret",
    "key",
    "jwt",
    "session",
    "csrf",
)
MAX_STRING_LENGTH = 800
MAX_MESSAGE_LENGTH = 3800
MAX_BODY_BYTES = 20000


def alerts_enabled():
    return bool(getattr(settings, "TELEGRAM_ERROR_ALERTS_ENABLED", False))


def _truncate(value, limit=MAX_STRING_LENGTH):
    text = str(value)
    if len(text) <= limit:
        return text
    return f"{text[:limit]}... [truncated]"


def _is_sensitive_key(key):
    normalized = str(key or "").strip().lower()
    return any(token in normalized for token in SENSITIVE_KEY_TOKENS)


def _mask_sensitive_value(value):
    if value is None:
        return "[redacted]"
    text = str(value)
    if len(text) <= 8:
        return "[redacted]"
    return f"{text[:4]}...{text[-4:]} [redacted]"


def sanitize_value(value, *, key=None, depth=0):
    if _is_sensitive_key(key):
        return _mask_sensitive_value(value)

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if depth > 4:
        return "[max-depth]"

    if isinstance(value, bytes):
        return _truncate(value.decode("utf-8", errors="replace"))

    if isinstance(value, str):
        return _truncate(value)

    if isinstance(value, (list, tuple, set)):
        return [sanitize_value(item, depth=depth + 1) for item in list(value)[:20]]

    if isinstance(value, dict):
        return {
            str(item_key): sanitize_value(item_value, key=item_key, depth=depth + 1)
            for item_key, item_value in list(value.items())[:50]
        }

    return _truncate(value)


def _parse_json_text(text):
    try:
        return json.loads(text)
    except Exception:
        return text


def _request_headers(request):
    headers = {}
    allowed = (
        "CONTENT_TYPE",
        "CONTENT_LENGTH",
        "HTTP_ORIGIN",
        "HTTP_REFERER",
        "HTTP_USER_AGENT",
        "HTTP_X_FORWARDED_FOR",
        "HTTP_X_REAL_IP",
    )
    for meta_key in allowed:
        value = request.META.get(meta_key)
        if value:
            headers[meta_key] = value
    auth_header = request.META.get("HTTP_AUTHORIZATION")
    if auth_header:
        headers["HTTP_AUTHORIZATION"] = _mask_sensitive_value(auth_header)
    return sanitize_value(headers)


def _uploaded_files_summary(request):
    if not getattr(request, "FILES", None):
        return None
    return [
        {
            "field": field_name,
            "name": uploaded_file.name,
            "size": uploaded_file.size,
            "content_type": getattr(uploaded_file, "content_type", ""),
        }
        for field_name, uploaded_file in request.FILES.items()
    ]


def _request_body(request):
    try:
        content_type = (request.content_type or "").lower()
        try:
            parsed_data = getattr(request, "data", None)
        except Exception:
            parsed_data = None
        if parsed_data not in (None, "") and not hasattr(parsed_data, "lists"):
            return sanitize_value(parsed_data)
        if "multipart/form-data" in content_type:
            form_data = dict(request.POST.lists())
            return {
                "form": sanitize_value(form_data),
                "files": _uploaded_files_summary(request),
            }
        if "application/x-www-form-urlencoded" in content_type:
            return sanitize_value(dict(request.POST.lists()))
        if parsed_data not in (None, ""):
            if hasattr(parsed_data, "lists"):
                return sanitize_value(dict(parsed_data.lists()))
            return sanitize_value(parsed_data)

        try:
            raw_body = request.body or b""
        except RawPostDataException:
            return None
        if not raw_body:
            return None
        if len(raw_body) > MAX_BODY_BYTES:
            raw_body = raw_body[:MAX_BODY_BYTES]
        decoded = raw_body.decode("utf-8", errors="replace")
        return sanitize_value(_parse_json_text(decoded))
    except Exception as exc:
        return {"body_error": _truncate(exc)}


def _request_user_info(request):
    user = getattr(request, "user", None)
    is_authenticated = bool(user and getattr(user, "is_authenticated", False))
    if not is_authenticated:
        return None
    return sanitize_value(
        {
            "idusuario": getattr(user, "idusuario", None),
            "correo": getattr(user, "correo", None),
            "is_staff": getattr(user, "is_staff", False),
            "is_superuser": getattr(user, "is_superuser", False),
        }
    )


def _request_context(request):
    return {
        "method": request.method,
        "path": request.path,
        "full_path": request.get_full_path(),
        "query_params": sanitize_value(dict(request.GET.lists())),
        "ip": get_client_ip(request),
        "user": _request_user_info(request),
        "headers": _request_headers(request),
        "body": _request_body(request),
    }


def _security_context(request):
    observation = getattr(request, "_security_observation", None)
    if not observation:
        return None
    action_label = {
        "counted": "contabilizado",
        "score": "score aumentado",
        "banned": "IP bloqueada",
    }.get(observation.get("action"), observation.get("action"))
    return sanitize_value(
        {
            "evento": observation.get("event_type"),
            "motivo": observation.get("reason"),
            "accion": action_label,
            "riesgo_sumado": observation.get("risk_delta"),
            "score_total_ip": observation.get("score_total"),
            "hits_ventana": observation.get("hits"),
            "status": observation.get("status_code"),
            "bloqueada": observation.get("blocked"),
        }
    )


def _response_body(response):
    data = getattr(response, "data", None)
    if data is not None:
        return sanitize_value(data)
    content = getattr(response, "content", b"")
    if not content:
        return None
    if len(content) > MAX_BODY_BYTES:
        content = content[:MAX_BODY_BYTES]
    return sanitize_value(content.decode("utf-8", errors="replace"))


def _format_message(title, sections):
    lines = [f"<b>{escape(title)}</b>"]
    for label, value in sections:
        if value in (None, "", {}, []):
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        safe_label = escape(str(label))
        safe_value = escape(_truncate(value, 1200))
        if safe_value.startswith("{") or safe_value.startswith("["):
          lines.append(f"\n<b>{safe_label}</b>\n<pre>{safe_value}</pre>")
        else:
          lines.append(f"\n<b>{safe_label}</b>\n<code>{safe_value}</code>")
    message = "\n".join(lines)
    if len(message) <= MAX_MESSAGE_LENGTH:
        return message
    return f"{message[:MAX_MESSAGE_LENGTH]}... [truncated]"


def _severity_emoji(status_code=None, *, frontend=False, exception=False):
    if exception:
        return "💥"
    if frontend:
        return "🧭"
    if status_code and int(status_code) >= 500:
        return "🔥"
    if status_code and int(status_code) >= 400:
        return "⚠️"
    return "ℹ️"


def _frontend_payload_context(frontend_payload):
    payload = frontend_payload.get("payload", {}) if isinstance(frontend_payload, dict) else {}
    request = payload.get("request", {}) if isinstance(payload, dict) else {}
    response = payload.get("response", {}) if isinstance(payload, dict) else {}
    error = payload.get("error", {}) if isinstance(payload, dict) else {}
    return {
        "route": payload.get("route") or frontend_payload.get("route"),
        "kind": payload.get("kind") or frontend_payload.get("kind"),
        "message": frontend_payload.get("message") or payload.get("message"),
        "action": payload.get("userAction") or frontend_payload.get("userAction"),
        "method": request.get("method"),
        "url": request.get("url"),
        "status": response.get("status"),
        "body": request.get("body"),
        "response_body": response.get("body"),
        "stack": error.get("stack"),
        "extra": payload.get("extra"),
    }


def send_telegram_alert(message):
    if not alerts_enabled():
        return False

    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
    chat_id = getattr(settings, "TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        requests.post(url, json=payload, timeout=10)
        return True
    except Exception:
        logger.exception("No se pudo enviar alerta a Telegram")
        return False


def should_report_response(request, response):
    if not alerts_enabled():
        return False
    if getattr(request, "_skip_error_reporting", False):
        return False
    if not str(request.path).startswith("/api/"):
        return False
    status_code = int(getattr(response, "status_code", 0) or 0)
    return status_code >= 400


def mark_reported(request):
    request._error_alert_reported = True


def already_reported(request):
    return bool(getattr(request, "_error_alert_reported", False))


def notify_backend_exception(request, exc):
    if not alerts_enabled() or getattr(request, "_skip_error_reporting", False):
        return
    request_context = _request_context(request)
    message = _format_message(
        f"{_severity_emoji(exception=True)} GeoHabita · Excepcion Backend",
        [
            ("Momento", format_datetime(datetime.utcnow())),
            ("Error", f"{exc.__class__.__name__}: {exc}"),
            ("Ruta", request_context.get("full_path")),
            ("Metodo", request_context.get("method")),
            ("IP", request_context.get("ip")),
            ("Usuario", request_context.get("user")),
            ("Payload", request_context.get("body")),
            ("Query", request_context.get("query_params")),
            ("Headers", request_context.get("headers")),
            ("Traceback", traceback.format_exc()),
        ],
    )
    if send_telegram_alert(message):
        mark_reported(request)


def notify_backend_response(request, response):
    security_action = None
    try:
        security_action = observe_security_response(request, response)
    except Exception:
        logger.exception("security_response_observer_failed path=%s", getattr(request, "path", ""))

    if not should_report_response(request, response) or already_reported(request):
        return _security_replacement_response(request, security_action)

    status_code = int(getattr(response, "status_code", 0) or 0)
    request_context = _request_context(request)
    title = f"{_severity_emoji(status_code)} GeoHabita · Respuesta API"
    if status_code >= 500:
        title = f"{_severity_emoji(status_code)} GeoHabita · Error Backend"

    message = _format_message(
        title,
        [
            ("Momento", format_datetime(datetime.utcnow())),
            ("Status", status_code),
            ("Ruta", request_context.get("full_path")),
            ("Metodo", request_context.get("method")),
            ("IP", request_context.get("ip")),
            ("Usuario", request_context.get("user")),
            ("Payload", request_context.get("body")),
            ("Query", request_context.get("query_params")),
            ("Seguridad WAF", _security_context(request)),
            ("Respuesta", _response_body(response)),
        ],
    )
    if send_telegram_alert(message):
        mark_reported(request)
    return _security_replacement_response(request, security_action)


def _security_replacement_response(request, security_action):
    observation = getattr(request, "_security_observation", None)
    if not observation:
        return None
    event_type = observation.get("event_type")
    if event_type in {"sensitive_response_path", "repeated_scanner_response", "ip_banned"}:
        reason = observation.get("reason") or "sensitive_response_path"
        version = get_security_config().version
        return JsonResponse(
            {"detail": "Request blocked.", "code": "security_blocked", "waf_version": version},
            status=403,
            headers={
                "X-Security-Block": str(reason),
                "X-Security-Layer": "response_observer",
                "X-WAF-Version": version,
            },
        )
    if security_action == "banned":
        version = get_security_config().version
        return JsonResponse(
            {"detail": "Request blocked.", "code": "security_blocked", "waf_version": version},
            status=403,
            headers={
                "X-Security-Block": "risk_score_threshold",
                "X-Security-Layer": "response_observer",
                "X-WAF-Version": version,
            },
        )
    return None


def notify_frontend_report(request, payload):
    if not alerts_enabled():
        return

    frontend_payload = sanitize_value(payload or {})
    frontend_context = _frontend_payload_context(frontend_payload)
    message = _format_message(
        f"{_severity_emoji(frontend=True)} GeoHabita · Error Frontend",
        [
            ("Momento", format_datetime(datetime.utcnow())),
            ("Vista", frontend_context.get("route")),
            ("Accion", frontend_context.get("action")),
            ("Tipo", frontend_context.get("kind")),
            ("Mensaje", frontend_context.get("message")),
            ("Endpoint", frontend_context.get("url")),
            ("Metodo", frontend_context.get("method")),
            ("Status", frontend_context.get("status")),
            ("Payload enviado", frontend_context.get("body")),
            ("Respuesta API", frontend_context.get("response_body")),
            ("Stack frontend", frontend_context.get("stack")),
            ("Contexto extra", frontend_context.get("extra")),
            ("Cliente", _request_context(request)),
            ("Reporte original", frontend_payload),
        ],
    )
    send_telegram_alert(message)
