from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone
from django.utils.html import strip_tags
from datetime import timedelta
import json
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
from api.models import Inmobiliaria, Proyecto, Usuario
from api.models import PasswordResetCode
from api.serializers import (
    InmobiliariaSerializer,
    LoginSerializer,
    ProyectoSerializer,
    UsuarioSerializer,
)
from api.throttling import (
    LoginRateThrottle,
    RefreshRateThrottle,
    RegisterRateThrottle,
    RecoveryRequestRateThrottle,
    RecoveryVerifyRateThrottle,
    RecoveryResetRateThrottle,
)
from api.views.permissions import IsSuperUser

SECRET_KEY = settings.SECRET_KEY
logger = logging.getLogger("api.recovery")


def _generate_otp_code():
    return f"{secrets.randbelow(1000000):06d}"


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
    data = {
        "correo": request.data.get("correo"),
        "password": request.data.get("password"),
        "nombre": request.data.get("nombre"),
        "estado": 1,
    }
    serializer = UsuarioSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
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
    return Response(
        {"message": "Usuario desactivado correctamente"}, status=status.HTTP_200_OK
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RegisterRateThrottle])
def register_inmobiliaria_usuario(request):
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
        "estado": 1,
    }
    usuario_serializer = UsuarioSerializer(data=usuario_data)
    if not usuario_serializer.is_valid():
        return Response(usuario_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        usuario = usuario_serializer.save()
        inmobiliaria_data = {
            "nombreinmobiliaria": request.data.get("nombreinmobiliaria"),
            "facebook": request.data.get("facebook"),
            "whatsapp": request.data.get("whatsapp"),
            "pagina": request.data.get("pagina"),
            "estado": 1,
            "idusuario": usuario.idusuario,
            "descripcion": request.data.get("descripcion"),
            "telefono": request.data.get("telefono"),
            "correo": request.data.get("correo"),
        }
        inmo_serializer = InmobiliariaSerializer(data=inmobiliaria_data)
        if not inmo_serializer.is_valid():
            transaction.set_rollback(True)
            return Response(inmo_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        inmo_serializer.save()

    return Response(
        {
            "usuario": UsuarioSerializer(usuario).data,
            "inmobiliaria": inmo_serializer.data,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RecoveryRequestRateThrottle])
def recovery_request_code(request):
    correo = _read_email_payload(request)
    logger.info("recovery_request_received correo=%s ip=%s", correo, request.META.get("REMOTE_ADDR"))
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
        request_ip=request.META.get("REMOTE_ADDR"),
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
    logger.info("recovery_verify_received correo=%s ip=%s", correo, request.META.get("REMOTE_ADDR"))

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
    logger.info("recovery_reset_received correo=%s ip=%s", correo, request.META.get("REMOTE_ADDR"))

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
    except Exception as exc:
        detail = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
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
    serializer = LoginSerializer(data=request.data, context={"request": request})
    if serializer.is_valid():
        usuario = serializer.validated_data["usuario"]
        refresh = RefreshToken.for_user(usuario)
        access = str(refresh.access_token)

        inmobiliaria = Inmobiliaria.objects.filter(idusuario=usuario).first()

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

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RefreshRateThrottle])
def refresh_token(request):
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

        return Response(
            {"access": str(new_refresh.access_token), "refresh": str(new_refresh)}
        )
    except TokenError:
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
    response = Response({"message": "Sesión cerrada"})
    response.delete_cookie("jwt")
    return response
