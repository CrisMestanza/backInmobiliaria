import ipaddress
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.http import HttpResponseBadRequest, HttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET

from api.models import BlockedIP, SecurityEvent
from api.security.conf import get_security_config, ip_is_whitelisted
from api.security.services import clear_block_cache

MANUAL_BLOCK_SALT = "geohabita.telegram.manual-block-ip"


def make_manual_block_token(ip_address, *, path="", method=""):
    ipaddress.ip_address(ip_address)
    config = get_security_config()
    if ip_is_whitelisted(ip_address, config.whitelist_ips):
        raise ValueError("whitelisted IPs cannot be blocked from Telegram actions")
    return signing.dumps(
        {
            "ip": ip_address,
            "path": str(path or "")[:500],
            "method": str(method or "")[:10],
        },
        salt=MANUAL_BLOCK_SALT,
        compress=True,
    )


def load_manual_block_token(token):
    max_age = int(getattr(settings, "TELEGRAM_SECURITY_ACTION_MAX_AGE_SECONDS", 86400))
    payload = signing.loads(token, salt=MANUAL_BLOCK_SALT, max_age=max_age)
    ip_address = str(payload.get("ip") or "")
    ipaddress.ip_address(ip_address)
    return {
        "ip": ip_address,
        "path": str(payload.get("path") or "")[:500],
        "method": str(payload.get("method") or "")[:10],
    }


@require_GET
def manual_block_ip(request):
    token = request.GET.get("token")
    if not token:
        return HttpResponseBadRequest("Token requerido.")

    try:
        payload = load_manual_block_token(token)
    except Exception:
        return HttpResponseBadRequest("Token invalido o expirado.")

    config = get_security_config()
    if ip_is_whitelisted(payload["ip"], config.whitelist_ips):
        return HttpResponseBadRequest("La IP esta en whitelist y no se puede bloquear desde Telegram.")

    minutes = int(getattr(settings, "TELEGRAM_MANUAL_BLOCK_MINUTES", 1440))
    now = timezone.now()
    expires_at = None if minutes <= 0 else now + timedelta(minutes=minutes)
    ip_address = payload["ip"]
    reason = "manual_telegram_block"

    BlockedIP.objects.update_or_create(
        ip_address=ip_address,
        defaults={
            "reason": reason,
            "risk_score": 999,
            "is_active": True,
            "is_permanent": expires_at is None,
            "expires_at": expires_at,
            "last_seen_at": now,
            "path": payload.get("path"),
        },
    )
    clear_block_cache(ip_address)
    SecurityEvent.objects.create(
        ip_address=ip_address,
        method=payload.get("method"),
        path=payload.get("path"),
        event_type="manual_telegram_block",
        risk_score=999,
        action="banned",
        reason=reason,
        metadata={"source": "telegram_button", "expires_at": expires_at.isoformat() if expires_at else None},
    )

    duration = "permanente" if expires_at is None else f"hasta {expires_at:%Y-%m-%d %H:%M:%S UTC}"
    return HttpResponse(f"IP {ip_address} bloqueada ({duration}).")
