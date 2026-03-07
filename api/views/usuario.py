from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone
from django.utils.html import strip_tags
from datetime import timedelta
from urllib.parse import urlencode
import json
import hashlib
import secrets
import re
import logging
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import ParseError
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from api.authentication import CustomJWTAuthentication
from api.audit import log_audit_event
from api.models import Inmobiliaria, Proyecto, Usuario
from api.models import PasswordResetCode, AccountActivationToken
from api.request_utils import get_client_ip
from api.serializers import (
    InmobiliariaSerializer,
    LoginSerializer,
    ProyectoSerializer,
    UsuarioSerializer,
)
from api.throttling import (
    ActivationResendRateThrottle,
    LoginRateThrottle,
    RefreshRateThrottle,
    RegisterRateThrottle,
    RecoveryRequestRateThrottle,
    RecoveryVerifyRateThrottle,
    RecoveryResetRateThrottle,
)
from api.validation_utils import (
    inmobiliaria_phone_exists_normalized,
    normalize_phone,
)
from api.views.permissions import IsSuperUser

SECRET_KEY = settings.SECRET_KEY
logger = logging.getLogger("api.recovery")
auth_logger = logging.getLogger("api.audit")


REAL_NAME_PART_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}")


def _generate_otp_code():
    return f"{secrets.randbelow(1000000):06d}"


def _normalize_phone(value):
    return normalize_phone(value)


def _is_realistic_name(value):
    name = (value or "").strip()
    if len(name) < 5:
        return False
    return len(REAL_NAME_PART_RE.findall(name)) >= 2


def _hash_activation_token(raw_token):
    return hashlib.sha256(f"{raw_token}{SECRET_KEY}".encode("utf-8")).hexdigest()


def _build_activation_link(user_id, raw_token):
    base_url = getattr(
        settings,
        "ACCOUNT_ACTIVATION_FRONTEND_URL",
        "https://www.geohabita.com/activar-cuenta",
    ).rstrip("/")
    return f"{base_url}?{urlencode({'uid': user_id, 'token': raw_token})}"


def _send_activation_email(destinatario, nombre, activation_link):
    subject = "GeoHabita - Activa tu cuenta"
    html = f"""
<div style="font-family: 'Segoe UI', Arial, sans-serif; background:#f6f8f7; padding:24px;">
  <div style="max-width:600px; margin:0 auto; background:#ffffff; border-radius:12px; border:1px solid #e2e8f0; overflow:hidden;">
    <div style="padding:24px; background:linear-gradient(135deg,#17a16e,#119b67); color:#fff;">
      <h1 style="margin:0; font-size:24px;">Activa tu cuenta</h1>
    </div>
    <div style="padding:24px;">
      <p style="color:#1e293b; margin:0 0 12px 0;">Hola {nombre},</p>
      <p style="color:#475569; margin:0 0 18px 0;">
        Tu cuenta fue creada correctamente. Para activarla y entrar al dashboard, confirma tu correo.
      </p>
      <a href="{activation_link}" style="display:inline-block; background:#17a16e; color:#fff; text-decoration:none; padding:12px 20px; border-radius:8px; font-weight:700;">
        Activar mi cuenta
      </a>
      <p style="color:#94a3b8; margin:18px 0 0 0; font-size:12px;">
        Si no solicitaste esta cuenta, ignora este correo.
      </p>
    </div>
  </div>
</div>
"""
    text = strip_tags(html)
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[destinatario],
    )
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)


def _create_activation_token(usuario, request):
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_activation_token(raw_token)
    ttl_hours = int(getattr(settings, "ACCOUNT_ACTIVATION_TTL_HOURS", 24))
    AccountActivationToken.objects.filter(
        idusuario=usuario,
        used_at__isnull=True,
    ).update(used_at=timezone.now())
    AccountActivationToken.objects.create(
        idusuario=usuario,
        token_hash=token_hash,
        expires_at=timezone.now() + timedelta(hours=ttl_hours),
        request_ip=get_client_ip(request),
    )
    return raw_token


def _build_recovery_profile(usuario):
    inmobiliaria = Inmobiliaria.objects.filter(idusuario=usuario).first()
    return {
        "usuario": {
            "idusuario": usuario.idusuario,
            "correo": usuario.correo,
            "nombre": usuario.nombre,
        },
        "inmobiliaria": {
            "idinmobiliaria": inmobiliaria.idinmobiliaria if inmobiliaria else None,
            "nombreinmobiliaria": inmobiliaria.nombreinmobiliaria if inmobiliaria else None,
            "telefono": inmobiliaria.telefono if inmobiliaria else None,
            "correo": inmobiliaria.correo if inmobiliaria else None,
            "whatsapp": inmobiliaria.whatsapp if inmobiliaria else None,
        },
    }


def _send_recovery_email(destinatario, codigo):
    subject = "GeoHabita - Codigo para recuperar tu contraseña"
    html = f"""
<div style="font-family: 'Segoe UI', Arial, sans-serif; background-color: #f6f8f7; padding: 20px; min-height: 100vh; display: flex; align-items: center; justify-content: center;">
  <div style="width: 100%; max-width: 600px; background: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid rgba(23,161,110,0.1); box-shadow: 0 20px 40px rgba(0,0,0,0.08);">

    <!-- Header -->
    <div style="background: linear-gradient(135deg, #17a16e, rgba(23,161,110,0.85)); padding: 24px 32px; text-align: center;">
      <div style="text-align: center; margin-bottom: 14px;">
        <div style="background: white; padding: 10px; border-radius: 12px; display: inline-block; margin-bottom: 8px;">
          <img
            src="https://www.geohabita.com/habitasinfondo.png"
            alt="GeoHabita"
            width="36"
            height="36"
            style="display: block; object-fit: contain;"
          />
        </div>
        <br/>
        <span style="color: white; font-size: 22px; font-weight: 800; letter-spacing: -0.5px;">GeoHabita</span>
      </div>
      <h1 style="color: white; font-size: 26px; font-weight: 700; margin: 0;">Recuperación de contraseña</h1>
    </div>

    <!-- Body -->
    <div style="padding: 28px 24px;">
      <div style="text-align: center; margin-bottom: 20px;">
        <h2 style="color: #1e293b; font-size: 20px; font-weight: 700; margin: 0 0 8px 0;">Restablece tu contraseña</h2>
        <p style="color: #64748b; line-height: 1.6; margin: 0;">
          Recibimos una solicitud para restablecer tu contraseña.<br>
          Usa el siguiente código de verificación. Expira en <strong>{settings.RECOVERY_CODE_TTL_MINUTES} minutos</strong>.
        </p>
      </div>

      <!-- OTP Boxes -->
      <table style="margin: 0 auto 20px auto; border-collapse: separate; border-spacing: 6px;">
        <tr>
          {"".join([
            f'<td style="width: 52px; height: 68px; background: rgba(23,161,110,0.08); border: 2px solid rgba(23,161,110,0.2); border-radius: 10px; text-align: center; vertical-align: middle;">'
            f'<span style="font-size: 28px; font-weight: 800; color: #17a16e;">{digit}</span>'
            f'</td>'
            for digit in str(codigo)
          ])}
        </tr>
      </table>

      <!-- Security note -->
      <div style="background: #f8fafc; border-radius: 8px; padding: 12px 16px; margin-bottom: 16px;">
        <p style="color: #94a3b8; font-size: 13px; font-style: italic; text-align: center; margin: 0;">
          Si no solicitaste este cambio, puedes ignorar este correo.
        </p>
      </div>

      <!-- Help -->
      <div style="text-align: center; padding-top: 16px; border-top: 1px solid #f1f5f9;">
        <p style="color: #1e293b; font-size: 13px; font-weight: 700; margin: 0 0 6px 0;">¿Necesitas ayuda?</p>
        <div style="display: flex; justify-content: center; gap: 16px;">
          <a href="https://wa.me/51916762676" target="_blank" style="color: #17a16e; font-size: 13px; font-weight: 600; text-decoration: none;">Contactar soporte WhatsApp</a>
          <span style="color: #cbd5e1;">•</span>
          <a href="#" style="color: #17a16e; font-size: 13px; font-weight: 600; text-decoration: none;">Centro de ayuda</a>
        </div>
      </div>
    </div>

    <!-- Footer -->
    <div style="background: #f8fafc; padding: 14px; text-align: center; border-top: 1px solid #f1f5f9;">
      <p style="color: #94a3b8; font-size: 11px; margin: 0;">© 2026 GeoHabita.com</p>
      <p style="color: #94a3b8; font-size: 11px; margin: 0;">Todos los derechos reservados.</p>
    </div>

  </div>
</div>
"""
    text = strip_tags(html)
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[destinatario],
    )
    msg.attach_alternative(html, "text/html")
    sent_count = msg.send(fail_silently=False)
    logger.info(
        "recovery_email_send_result to=%s sent_count=%s smtp_host=%s smtp_port=%s",
        destinatario,
        sent_count,
        getattr(settings, "EMAIL_HOST", ""),
        getattr(settings, "EMAIL_PORT", ""),
    )


def _safe_payload(request):
    try:
        data = request.data
        if isinstance(data, dict):
            return data
    except ParseError:
        pass

    raw = (request.body or b"").decode("utf-8", errors="ignore").strip()
    if not raw:
        return {}

    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        # Soporta formato tipo JS: {correo: "a@b.com"}
        match = re.search(
            r'(correo|email|usuario)\s*:\s*[\'"]([^\'"]+)[\'"]',
            raw,
            re.IGNORECASE,
        )
        if match:
            return {match.group(1).lower(): match.group(2).strip()}
        return {}


def _read_email_payload(request):
    payload = _safe_payload(request)
    return (
        payload.get("correo")
        or payload.get("email")
        or payload.get("usuario")
        or ""
    ).strip().lower()


@api_view(["GET"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated, IsSuperUser])
def listUsuarios(request):
    usuarios = Usuario.objects.filter(estado=1)
    serializer = UsuarioSerializer(usuarios, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated, IsSuperUser])
def registerUsuario(request):
    client_ip = get_client_ip(request)
    data = {
        "correo": request.data.get("correo"),
        "password": request.data.get("password"),
        "nombre": request.data.get("nombre"),
        "estado": 0,
    }
    if not _is_realistic_name(data.get("nombre")):
        return Response(
            {"nombre": ["Debes ingresar al menos nombre y apellido reales."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    serializer = UsuarioSerializer(data=data)
    if serializer.is_valid():
        usuario_instance = serializer.save()
        if not isinstance(usuario_instance, Usuario):
            return Response(
                {"message": "No se pudo crear el usuario."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        usuario = usuario_instance
        raw_token = _create_activation_token(usuario, request)
        activation_link = _build_activation_link(usuario.idusuario, raw_token)
        try:
            _send_activation_email(usuario.correo, usuario.nombre or "usuario", activation_link)
        except Exception:
            logger.exception(
                "activation_email_error usuario_id=%s correo=%s ip=%s",
                usuario.idusuario,
                usuario.correo,
                client_ip,
            )
            return Response(
                {"message": "Cuenta creada, pero no se pudo enviar el correo de activación."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        auth_logger.info(
            "register_usuario_pending_activation usuario_id=%s correo=%s ip=%s",
            usuario.idusuario,
            usuario.correo,
            client_ip,
        )
        log_audit_event(
            request,
            "user_register_pending_activation",
            status_code=status.HTTP_201_CREATED,
            success=True,
            target_resource="usuario",
            target_id=usuario.idusuario,
            detail={"correo": usuario.correo},
        )
        return Response(
            {
                "message": (
                    f'Tu cuenta ha sido creada, por favor confirma la activación que te llegó al correo: "{usuario.correo}".'
                ),
                "activation_required": True,
            },
            status=status.HTTP_201_CREATED,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def listUsuarioId(request, idusuario):
    if request.user.idusuario != idusuario and not request.user.is_superuser:
        return Response(
            {"error": "No tienes permisos para ver este usuario"},
            status=status.HTTP_403_FORBIDDEN,
        )

    usuario = Usuario.objects.filter(idusuario=idusuario, estado=1).first()
    if usuario:
        serializer = UsuarioSerializer(usuario)
        return Response(serializer.data)
    return Response(
        {"error": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND
    )


@api_view(["PUT"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def updateUsuario(request, idusuario):
    if request.user.idusuario != idusuario and not request.user.is_superuser:
        return Response(
            {"error": "No tienes permisos para editar este usuario"},
            status=status.HTTP_403_FORBIDDEN,
        )

    usuario = Usuario.objects.filter(idusuario=idusuario).first()
    if not usuario:
        return Response(
            {"error": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND
        )

    forbidden_privilege_fields = {
        "is_superuser",
        "is_staff",
        "is_active",
        "groups",
        "user_permissions",
    }
    if any(field in request.data for field in forbidden_privilege_fields):
        return Response(
            {"error": "No puedes modificar campos de privilegios."},
            status=status.HTTP_403_FORBIDDEN,
        )

    payload = {}
    if request.user.is_superuser:
        allowed_fields = {"correo", "nombre", "password", "estado"}
    else:
        allowed_fields = {"nombre", "password"}

    for key in allowed_fields:
        if key in request.data:
            payload[key] = request.data.get(key)

    if request.user.is_superuser and "estado" in payload:
        usuario.estado = int(payload.pop("estado"))
        usuario.save(update_fields=["estado"])

    serializer = UsuarioSerializer(usuario, data=payload, partial=True)
    if serializer.is_valid():
        serializer.save()
        log_audit_event(
            request,
            "user_update",
            status_code=status.HTTP_200_OK,
            success=True,
            target_resource="usuario",
            target_id=idusuario,
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["PUT"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def deleteUsuario(request, idusuario):
    if request.user.idusuario != idusuario and not request.user.is_superuser:
        return Response(
            {"error": "No tienes permisos para eliminar este usuario"},
            status=status.HTTP_403_FORBIDDEN,
        )

    usuario = Usuario.objects.filter(idusuario=idusuario).first()
    if not usuario:
        return Response(
            {"error": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND
        )

    usuario.estado = 0
    usuario.save(update_fields=["estado"])
    log_audit_event(
        request,
        "user_soft_delete",
        status_code=status.HTTP_200_OK,
        success=True,
        target_resource="usuario",
        target_id=idusuario,
    )
    return Response(
        {"message": "Usuario desactivado correctamente"}, status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RegisterRateThrottle])
def register_inmobiliaria_usuario(request):
    client_ip = get_client_ip(request)
    usuario_payload = request.data.get("usuario")
    if isinstance(usuario_payload, str):
        try:
            usuario_payload = json.loads(usuario_payload)
        except json.JSONDecodeError:
            return Response(
                {"usuario": ["Debe ser JSON válido."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
    if usuario_payload is None:
        usuario_payload = {}
    if not isinstance(usuario_payload, dict):
        return Response(
            {"usuario": ["Debe ser un objeto con correo, nombre y password."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    usuario_data = {
        "correo": usuario_payload.get("correo") or request.data.get("correo"),
        "password": usuario_payload.get("password") or request.data.get("password"),
        "nombre": usuario_payload.get("nombre") or request.data.get("nombre"),
        "estado": 0,
    }
    if not _is_realistic_name(usuario_data.get("nombre")):
        return Response(
            {"usuario": {"nombre": ["Debes ingresar al menos nombre y apellido reales."]}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    telefono = (request.data.get("telefono") or "").strip()
    telefono_digits = _normalize_phone(telefono)
    if not telefono:
        return Response(
            {"telefono": ["El número de teléfono es obligatorio."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(telefono_digits) < 7 or len(telefono_digits) > 15:
        return Response(
            {"telefono": ["El número de teléfono no es válido."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if inmobiliaria_phone_exists_normalized(telefono_digits):
        return Response(
            {"telefono": ["Este número ya está registrado."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    inmo_correo = (request.data.get("correo") or "").strip().lower()
    if not inmo_correo:
        return Response(
            {"correo": ["El correo de contacto de la inmobiliaria es obligatorio."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if Inmobiliaria.objects.filter(correo__iexact=inmo_correo).exists():
        return Response(
            {"correo": ["Este correo de contacto ya está registrado."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    usuario_serializer = UsuarioSerializer(data=usuario_data)
    if not usuario_serializer.is_valid():
        return Response(usuario_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        usuario_instance = usuario_serializer.save()
        if not isinstance(usuario_instance, Usuario):
            return Response(
                {"usuario": ["No se pudo crear el usuario."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        usuario = usuario_instance
        inmobiliaria_data = {
            "nombreinmobiliaria": request.data.get("nombreinmobiliaria"),
            "facebook": request.data.get("facebook"),
            "whatsapp": request.data.get("whatsapp"),
            "tiktok": request.data.get("tiktok"),
            "pagina": request.data.get("pagina"),
            "estado": 0,
            "idusuario": usuario.idusuario,
            "descripcion": request.data.get("descripcion"),
            "telefono": telefono,
            "correo": inmo_correo,
        }
        inmo_serializer = InmobiliariaSerializer(data=inmobiliaria_data)
        if not inmo_serializer.is_valid():
            transaction.set_rollback(True)
            return Response(inmo_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        inmo_serializer.save()
        raw_token = _create_activation_token(usuario, request)

    activation_link = _build_activation_link(usuario.idusuario, raw_token)
    try:
        _send_activation_email(usuario.correo, usuario.nombre or "usuario", activation_link)
    except Exception:
        logger.exception(
            "activation_email_error usuario_id=%s correo=%s ip=%s",
            usuario.idusuario,
            usuario.correo,
            client_ip,
        )
        return Response(
            {"message": "Cuenta creada, pero no se pudo enviar el correo de activación."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    log_audit_event(
        request,
        "inmobiliaria_usuario_register_pending_activation",
        status_code=status.HTTP_201_CREATED,
        success=True,
        target_resource="usuario",
        target_id=usuario.idusuario,
        detail={"correo": usuario.correo},
    )

    return Response(
        {
            "message": (
                f'Tu cuenta ha sido creada, por favor confirma la activación que te llegó al correo: "{usuario.correo}".'
            ),
            "activation_required": True,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def confirm_account_activation(request):
    payload = _safe_payload(request)
    user_id = payload.get("uid")
    token = (payload.get("token") or "").strip()
    client_ip = get_client_ip(request)

    if not user_id or not token:
        return Response(
            {"message": "Enlace de activación inválido."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    usuario = Usuario.objects.filter(idusuario=user_id).first()
    if not usuario:
        return Response(
            {"message": "Cuenta no encontrada."},
            status=status.HTTP_404_NOT_FOUND,
        )

    if usuario.is_active and usuario.estado == 1:
        return Response(
            {"message": "Tu cuenta ya está activa."},
            status=status.HTTP_200_OK,
        )

    token_hash = _hash_activation_token(token)
    activation_entry = (
        AccountActivationToken.objects.filter(
            idusuario=usuario,
            token_hash=token_hash,
            used_at__isnull=True,
        )
        .order_by("-created_at")
        .first()
    )

    if not activation_entry:
        return Response(
            {"message": "El enlace de activación no es válido."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if activation_entry.expires_at < timezone.now():
        return Response(
            {"message": "El enlace de activación expiró. Solicita uno nuevo."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    usuario.is_active = True
    usuario.estado = 1
    usuario.save(update_fields=["is_active", "estado"])
    activation_entry.used_at = timezone.now()
    activation_entry.request_ip = client_ip
    activation_entry.save(update_fields=["used_at", "request_ip"])
    auth_logger.info(
        "account_activated usuario_id=%s correo=%s ip=%s",
        usuario.idusuario,
        usuario.correo,
        client_ip,
    )
    log_audit_event(
        request,
        "account_activation_confirmed",
        status_code=status.HTTP_200_OK,
        success=True,
        target_resource="usuario",
        target_id=usuario.idusuario,
        detail={"correo": usuario.correo},
    )
    return Response(
        {"message": "Cuenta activada correctamente. Ya puedes iniciar sesión."},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([ActivationResendRateThrottle])
def resend_account_activation(request):
    correo = _read_email_payload(request)
    client_ip = get_client_ip(request)
    generic_ok = {
        "message": "Si el correo está pendiente de activación, enviaremos un nuevo enlace."
    }

    if not correo:
        return Response(
            {"message": "El correo es obligatorio."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    usuario = Usuario.objects.filter(correo__iexact=correo).first()
    if not usuario:
        auth_logger.info("activation_resend_user_not_found correo=%s ip=%s", correo, client_ip)
        return Response(generic_ok, status=status.HTTP_200_OK)

    if usuario.is_active and usuario.estado == 1:
        return Response(
            {"message": "Tu cuenta ya está activa. Puedes iniciar sesión."},
            status=status.HTTP_200_OK,
        )

    raw_token = _create_activation_token(usuario, request)
    activation_link = _build_activation_link(usuario.idusuario, raw_token)

    try:
        _send_activation_email(usuario.correo, usuario.nombre or "usuario", activation_link)
    except Exception:
        logger.exception(
            "activation_resend_email_error usuario_id=%s correo=%s ip=%s",
            usuario.idusuario,
            usuario.correo,
            client_ip,
        )
        return Response(
            {"message": "No se pudo enviar el correo en este momento."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    auth_logger.info(
        "activation_resend_success usuario_id=%s correo=%s ip=%s",
        usuario.idusuario,
        usuario.correo,
        client_ip,
    )
    log_audit_event(
        request,
        "account_activation_resent",
        status_code=status.HTTP_200_OK,
        success=True,
        target_resource="usuario",
        target_id=usuario.idusuario,
        detail={"correo": usuario.correo},
    )
    return Response(generic_ok, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RecoveryRequestRateThrottle])
def recovery_request_code(request):
    correo = _read_email_payload(request)
    client_ip = get_client_ip(request)
    logger.info("recovery_request_received correo=%s ip=%s", correo, client_ip)
    generic_ok = {
        "message": "Si el correo está registrado, enviaremos un código de recuperación."
    }
    if not correo:
        return Response(
            {"message": "El correo es obligatorio."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    usuario = (
        Usuario.objects.filter(correo=correo, estado=1, is_active=True)
        .only("idusuario", "correo")
        .first()
    )
    if not usuario:
        logger.warning("recovery_request_user_not_found correo=%s", correo)
        return Response(generic_ok, status=status.HTTP_200_OK)

    now = timezone.now()
    cooldown = int(getattr(settings, "RECOVERY_CODE_COOLDOWN_SECONDS", 60))
    last_request = (
        PasswordResetCode.objects.filter(idusuario=usuario)
        .order_by("-created_at")
        .only("created_at")
        .first()
    )
    if last_request and (now - last_request.created_at).total_seconds() < cooldown:
        remaining = cooldown - int((now - last_request.created_at).total_seconds())
        logger.info(
            "recovery_request_cooldown usuario_id=%s correo=%s remaining_seconds=%s",
            usuario.idusuario,
            usuario.correo,
            max(0, remaining),
        )
        return Response(generic_ok, status=status.HTTP_200_OK)

    code = _generate_otp_code()
    ttl_minutes = int(getattr(settings, "RECOVERY_CODE_TTL_MINUTES", 10))

    PasswordResetCode.objects.create(
        idusuario=usuario,
        codigo_hash=make_password(code),
        expires_at=now + timedelta(minutes=ttl_minutes),
        request_ip=client_ip,
    )
    logger.info(
        "recovery_code_created usuario_id=%s correo=%s expires_minutes=%s",
        usuario.idusuario,
        usuario.correo,
        ttl_minutes,
    )

    try:
        _send_recovery_email(usuario.correo, code)
    except Exception:
        logger.exception("recovery_email_send_error usuario_id=%s correo=%s", usuario.idusuario, usuario.correo)
        return Response(
            {"message": "No se pudo enviar el correo en este momento."},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    logger.info("recovery_request_success usuario_id=%s correo=%s", usuario.idusuario, usuario.correo)
    return Response(generic_ok, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RecoveryVerifyRateThrottle])
def recovery_verify_code(request):
    payload = _safe_payload(request)
    correo = _read_email_payload(request)
    codigo = (payload.get("codigo") or "").strip()
    logger.info("recovery_verify_received correo=%s ip=%s", correo, get_client_ip(request))

    if not correo or not codigo:
        return Response(
            {"message": "Correo y código son obligatorios."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    usuario = (
        Usuario.objects.filter(correo=correo, estado=1, is_active=True)
        .only("idusuario", "correo", "nombre")
        .first()
    )
    if not usuario:
        logger.warning("recovery_verify_user_not_found correo=%s", correo)
        return Response(
            {"message": "Código inválido o expirado."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    reset_entry = (
        PasswordResetCode.objects.filter(idusuario=usuario, used_at__isnull=True)
        .order_by("-created_at")
        .first()
    )
    if not reset_entry or reset_entry.expires_at < timezone.now():
        logger.warning("recovery_verify_code_missing_or_expired usuario_id=%s correo=%s", usuario.idusuario, correo)
        return Response(
            {"message": "Código inválido o expirado."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    max_attempts = int(getattr(settings, "RECOVERY_CODE_MAX_ATTEMPTS", 5))
    if reset_entry.attempts >= max_attempts:
        logger.warning("recovery_verify_max_attempts usuario_id=%s correo=%s attempts=%s", usuario.idusuario, correo, reset_entry.attempts)
        return Response(
            {"message": "Superaste el número de intentos permitidos."},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )

    if not check_password(codigo, reset_entry.codigo_hash):
        reset_entry.attempts += 1
        reset_entry.save(update_fields=["attempts"])
        logger.warning(
            "recovery_verify_wrong_code usuario_id=%s correo=%s attempts=%s",
            usuario.idusuario,
            correo,
            reset_entry.attempts,
        )
        return Response(
            {"message": "Código inválido o expirado."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    reset_entry.verified_at = timezone.now()
    reset_entry.reset_token = secrets.token_urlsafe(32)
    reset_entry.save(update_fields=["verified_at", "reset_token"])
    logger.info("recovery_verify_success usuario_id=%s correo=%s", usuario.idusuario, correo)

    profile = _build_recovery_profile(usuario)
    return Response(
        {
            "message": "Código verificado correctamente.",
            "reset_token": reset_entry.reset_token,
            **profile,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RecoveryResetRateThrottle])
def recovery_reset_password(request):
    payload = _safe_payload(request)
    correo = _read_email_payload(request)
    reset_token = (payload.get("reset_token") or "").strip()
    password = payload.get("password") or ""
    logger.info("recovery_reset_received correo=%s ip=%s", correo, get_client_ip(request))

    if not correo or not reset_token or not password:
        return Response(
            {"message": "Correo, token y contraseña son obligatorios."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    usuario = Usuario.objects.filter(correo=correo, estado=1, is_active=True).first()
    if not usuario:
        logger.warning("recovery_reset_user_not_found correo=%s", correo)
        return Response(
            {"message": "Solicitud inválida."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    reset_entry = (
        PasswordResetCode.objects.filter(
            idusuario=usuario,
            reset_token=reset_token,
            used_at__isnull=True,
            verified_at__isnull=False,
        )
        .order_by("-created_at")
        .first()
    )

    if not reset_entry or reset_entry.expires_at < timezone.now():
        logger.warning("recovery_reset_invalid_or_expired usuario_id=%s correo=%s", usuario.idusuario, correo)
        return Response(
            {"message": "La sesión de recuperación expiró. Solicita un nuevo código."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        validate_password(password, user=usuario)
    except ValidationError as exc:
        detail = exc.messages[0] if exc.messages else str(exc)
        return Response({"message": detail}, status=status.HTTP_400_BAD_REQUEST)

    usuario.set_password(password)
    usuario.save(update_fields=["password"])
    logger.info("recovery_reset_password_updated usuario_id=%s correo=%s", usuario.idusuario, correo)

    reset_entry.used_at = timezone.now()
    reset_entry.reset_token = None
    reset_entry.save(update_fields=["used_at", "reset_token"])

    return Response(
        {"message": "Contraseña actualizada correctamente."},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([LoginRateThrottle])
def login_usuario(request):
    client_ip = get_client_ip(request)
    auth_logger.info("login_attempt ip=%s", client_ip)
    serializer = LoginSerializer(data=request.data, context={"request": request})
    if serializer.is_valid():
        validated_data = serializer.validated_data or {}
        if not isinstance(validated_data, dict):
            validated_data = {}
        usuario = validated_data.get("usuario")
        if not isinstance(usuario, Usuario):
            return Response(
                {"detail": "Credenciales inválidas"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        refresh = RefreshToken.for_user(usuario)
        access = str(refresh.access_token)

        inmobiliaria = Inmobiliaria.objects.filter(idusuario=usuario).first()
        log_audit_event(
            request,
            "login_success",
            status_code=status.HTTP_200_OK,
            success=True,
            target_resource="usuario",
            target_id=usuario.idusuario,
            detail={"correo": usuario.correo},
        )

        return Response(
            {
                "refresh": str(refresh),
                "access": access,
                "usuario": {
                    "idusuario": usuario.idusuario,
                    "correo": usuario.correo,
                    "nombre": usuario.nombre,
                },
                "inmobiliaria": {
                    "idinmobiliaria": inmobiliaria.idinmobiliaria
                    if inmobiliaria
                    else None,
                    "nombreinmobiliaria": inmobiliaria.nombreinmobiliaria
                    if inmobiliaria
                    else None,
                }
                if inmobiliaria
                else None,
            },
            status=status.HTTP_200_OK,
        )
    auth_logger.info("login_failed ip=%s", client_ip)
    log_audit_event(
        request,
        "login_failed",
        status_code=status.HTTP_400_BAD_REQUEST,
        success=False,
        target_resource="usuario",
        detail={"payload_keys": list((request.data or {}).keys()) if hasattr(request, "data") else []},
    )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RefreshRateThrottle])
def refresh_token(request):
    client_ip = get_client_ip(request)
    token = request.data.get("refresh")
    if not token:
        return Response(
            {"detail": "Token no proporcionado"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        old_refresh = RefreshToken(token)
        user_id = old_refresh.get("user_id")
        if not user_id:
            return Response(
                {"detail": "Token inválido"}, status=status.HTTP_401_UNAUTHORIZED
            )

        user = Usuario.objects.filter(
            idusuario=user_id, estado=1, is_active=True
        ).first()
        if not user:
            return Response(
                {"detail": "Usuario inactivo o no encontrado"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        new_refresh = RefreshToken.for_user(user)
        if getattr(settings, "SIMPLE_JWT", {}).get("BLACKLIST_AFTER_ROTATION", False):
            try:
                old_refresh.blacklist()
            except Exception:
                pass

        log_audit_event(
            request,
            "refresh_success",
            status_code=status.HTTP_200_OK,
            success=True,
            target_resource="usuario",
            target_id=user.idusuario,
            detail={"correo": user.correo},
        )
        return Response(
            {"access": str(new_refresh.access_token), "refresh": str(new_refresh)}
        )
    except TokenError:
        auth_logger.info("refresh_failed ip=%s reason=token_error", client_ip)
        log_audit_event(
            request,
            "refresh_failed",
            status_code=status.HTTP_401_UNAUTHORIZED,
            success=False,
            target_resource="usuario",
        )
        return Response(
            {"detail": "Token inválido"}, status=status.HTTP_401_UNAUTHORIZED
        )


@api_view(["GET"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def mis_proyectos(request):
    inmobiliaria = Inmobiliaria.objects.filter(idusuario=request.user).first()
    if not inmobiliaria:
        return Response(
            {"detail": "No tiene inmobiliaria asociada"},
            status=status.HTTP_403_FORBIDDEN,
        )

    proyectos = Proyecto.objects.filter(idinmobiliaria=inmobiliaria.idinmobiliaria)
    serializer = ProyectoSerializer(proyectos, many=True)
    return Response(serializer.data)


class CheckAuthView(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            {
                "detail": "Token válido",
                "idusuario": user.idusuario,
                "correo": user.correo,
                "nombre": user.nombre,
            },
            status=status.HTTP_200_OK,
        )


@api_view(["POST"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def logout(request):
    auth_logger.info("logout user_id=%s ip=%s", getattr(request.user, "idusuario", None), get_client_ip(request))
    log_audit_event(
        request,
        "logout",
        status_code=status.HTTP_200_OK,
        success=True,
        target_resource="usuario",
        target_id=getattr(request.user, "idusuario", None),
    )
    response = Response({"message": "Sesión cerrada"})
    response.delete_cookie("jwt")
    return response
