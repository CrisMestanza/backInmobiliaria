from django.conf import settings
from django.db import transaction
import json
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
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from api.authentication import CustomJWTAuthentication
from api.models import Inmobiliaria, Proyecto, Usuario
from api.serializers import (
    InmobiliariaSerializer,
    LoginSerializer,
    ProyectoSerializer,
    UsuarioSerializer,
)
from api.throttling import LoginRateThrottle, RefreshRateThrottle, RegisterRateThrottle
from api.views.permissions import IsSuperUser

SECRET_KEY = settings.SECRET_KEY


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
