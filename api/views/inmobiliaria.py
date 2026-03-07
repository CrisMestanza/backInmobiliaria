import hashlib
import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Prefetch
from django.utils import timezone
from django.utils.html import strip_tags
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.authentication import CustomJWTAuthentication
from api.audit import log_audit_event
from api.models import AccountActivationToken, Inmobiliaria, Lote, Puntos, PuntosProyecto
from api.request_utils import get_client_ip
from api.serializers import (
    InmobiliariaRegistroSerializer,
    InmobiliariaSerializer,
    LoteSerializer,
    PuntosProyectoSerializer,
    PuntosSerializer,
)
from api.throttling import RegisterRateThrottle
from api.validation_utils import (
    inmobiliaria_phone_exists_normalized,
    normalize_phone,
)

logger = logging.getLogger("api.audit")


def _hash_activation_token(raw_token):
    return hashlib.sha256(f"{raw_token}{settings.SECRET_KEY}".encode("utf-8")).hexdigest()


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
    ttl_hours = int(getattr(settings, "ACCOUNT_ACTIVATION_TTL_HOURS", 24))
    AccountActivationToken.objects.filter(
        idusuario=usuario,
        used_at__isnull=True,
    ).update(used_at=timezone.now())
    AccountActivationToken.objects.create(
        idusuario=usuario,
        token_hash=_hash_activation_token(raw_token),
        expires_at=timezone.now() + timedelta(hours=ttl_hours),
        request_ip=get_client_ip(request),
    )
    return raw_token


@api_view(["GET"])
@permission_classes([AllowAny])
def list_inmobiliarias(_request):
    inmobiliarias = Inmobiliaria.objects.all()
    serializer = InmobiliariaSerializer(inmobiliarias, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def list_puntos(_request, idlote):
    puntos = Puntos.objects.filter(idlote=idlote)
    serializer = PuntosSerializer(puntos, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def list_puntos_por_proyecto(_request, idproyecto):
    """
    Retorna todos los puntos agrupados por lote para un proyecto.
    """
    # Traer los lotes del proyecto
    lotes = (
        Lote.objects.filter(idproyecto=idproyecto)
        .only("idlote", "nombre", "descripcion", "precio", "vendido")
        .prefetch_related(
            Prefetch(
                "puntos_set",
                queryset=Puntos.objects.only(
                    "idlote_id", "latitud", "longitud", "orden"
                ).order_by("orden"),
            )
        )
    )

    data = []
    for lote in lotes:
        data.append(
            {
                "id": lote.idlote,
                "nombre": lote.nombre,
                "descripcion": lote.descripcion,
                "precio": lote.precio,
                "vendido": lote.vendido,
                "puntos": PuntosSerializer(lote.puntos_set.all(), many=True).data,
            }
        )

    return Response(data)


@api_view(["GET"])
@permission_classes([AllowAny])
def list_puntosproyecto(_request, idproyecto):
    puntos = PuntosProyecto.objects.filter(idproyecto=idproyecto)
    serializer = PuntosProyectoSerializer(puntos, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([AllowAny])
def validar_lote(request, idproyecto):
    puntos_proyecto = list(
        PuntosProyecto.objects.filter(idproyecto=idproyecto).values_list(
            "latitud", "longitud"
        )
    )
    puntos_lote = request.data.get("puntos", [])
    # usar shapely para validar
    from shapely.geometry import Polygon

    poly_proyecto = Polygon(puntos_proyecto)
    poly_lote = Polygon(
        [(float(p["latitud"]), float(p["longitud"])) for p in puntos_lote]
    )
    valido = poly_proyecto.contains(poly_lote)
    return Response({"valido": valido})


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([RegisterRateThrottle])
def registrar_inmobiliaria(request):
    telefono = (request.data.get("telefono") or "").strip()
    correo_contacto = (request.data.get("correo") or "").strip().lower()
    telefono_digits = normalize_phone(telefono)
    if not telefono:
        return Response({"telefono": ["El número de teléfono es obligatorio."]}, status=400)
    if len(telefono_digits) < 7 or len(telefono_digits) > 15:
        return Response({"telefono": ["El número de teléfono no es válido."]}, status=400)
    if inmobiliaria_phone_exists_normalized(telefono_digits):
        return Response({"telefono": ["Este número ya está registrado."]}, status=400)
    if not correo_contacto:
        return Response({"correo": ["El correo de contacto es obligatorio."]}, status=400)
    if Inmobiliaria.objects.filter(correo__iexact=correo_contacto).exists():
        return Response({"correo": ["Este correo de contacto ya está registrado."]}, status=400)

    serializer = InmobiliariaRegistroSerializer(data=request.data)
    if serializer.is_valid():
        inmobiliaria = serializer.save()
        usuario = inmobiliaria.idusuario
        raw_token = _create_activation_token(usuario, request)
        activation_link = _build_activation_link(usuario.idusuario, raw_token)
        try:
            _send_activation_email(usuario.correo, usuario.nombre or "usuario", activation_link)
        except Exception:
            logger.exception(
                "activation_email_error usuario_id=%s correo=%s ip=%s",
                usuario.idusuario,
                usuario.correo,
                get_client_ip(request),
            )
            return Response(
                {"message": "Cuenta creada, pero no se pudo enviar el correo de activación."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        log_audit_event(
            request,
            "inmobiliaria_register_pending_activation",
            status_code=201,
            success=True,
            target_resource="inmobiliaria",
            target_id=getattr(inmobiliaria, "idinmobiliaria", None),
            detail={"usuario_id": usuario.idusuario, "correo": usuario.correo},
        )
        return Response(
            {
                "message": (
                    f'Tu cuenta ha sido creada, por favor confirma la activación que te llegó al correo: "{usuario.correo}".'
                ),
                "activation_required": True,
            },
            status=201,
        )
    log_audit_event(
        request,
        "inmobiliaria_register_failed",
        status_code=400,
        success=False,
        target_resource="inmobiliaria",
        detail=serializer.errors,
    )
    print("❌ Errores:", serializer.errors)
    return Response(serializer.errors, status=400)


@api_view(["GET"])
@permission_classes([AllowAny])
def list_inmobiliarias_id(_request, idlote):
    lote = Lote.objects.filter(idlote=idlote)
    serializer = LoteSerializer(lote, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def getInmobiliaria(request, idinmobiliaria):
    inmobiliarias = Inmobiliaria.objects.filter(idinmobiliaria=idinmobiliaria)
    serializer = InmobiliariaSerializer(inmobiliarias, many=True)
    return Response(serializer.data)


@api_view(["PUT"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def updateInmobiliaria(request, idinmobiliaria):
    try:
        inmobiliaria = Inmobiliaria.objects.get(idinmobiliaria=idinmobiliaria)
    except Inmobiliaria.DoesNotExist:
        return Response(
            {"error": "Inmobiliaria no encontrada"}, status=status.HTTP_404_NOT_FOUND
        )

    if inmobiliaria.idusuario_id != request.user.idusuario:
        return Response(
            {"error": "No tienes permisos para editar esta inmobiliaria"},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = InmobiliariaSerializer(inmobiliaria, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        log_audit_event(
            request,
            "inmobiliaria_update",
            status_code=200,
            success=True,
            target_resource="inmobiliaria",
            target_id=idinmobiliaria,
        )
        return Response(serializer.data, status=200)
    return Response(serializer.errors, status=400)


@api_view(["PUT"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def deleteInmobiliaria(request, idinmobiliaria):
    try:
        inmobiliaria = Inmobiliaria.objects.get(idinmobiliaria=idinmobiliaria)
    except Inmobiliaria.DoesNotExist:
        return Response(
            {"error": "Inmobiliaria no encontrada"}, status=status.HTTP_404_NOT_FOUND
        )

    if inmobiliaria.idusuario_id != request.user.idusuario:
        return Response(
            {"error": "No tienes permisos para eliminar esta inmobiliaria"},
            status=status.HTTP_403_FORBIDDEN,
        )

    inmobiliaria.estado = 0
    inmobiliaria.save()
    log_audit_event(
        request,
        "inmobiliaria_soft_delete",
        status_code=status.HTTP_200_OK,
        success=True,
        target_resource="inmobiliaria",
        target_id=idinmobiliaria,
    )
    return Response(
        {"message": "Inmobiliaria desactivada correctamente"}, status=status.HTTP_200_OK
    )
