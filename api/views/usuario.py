from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from ..serializers import UsuarioSerializer, InmobiliariaSerializer, ProyectoSerializer, LoginSerializer
from ..models import Usuario
from rest_framework import status
import json
from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
import datetime
import jwt
from ..models import Inmobiliaria, Proyecto
from django.conf import settings 
from django.contrib.auth.hashers import make_password, check_password
SECRET_KEY = settings.SECRET_KEY
from functools import wraps
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import RefreshToken, UntypedToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from rest_framework.decorators import authentication_classes
from ..authentication import CustomJWTAuthentication
import sys
sys.stdout.reconfigure(encoding='utf-8')

def jwt_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        token = request.COOKIES.get("jwt")
        if not token:
            return Response({"error": "No autenticado"}, status=401)
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            user = Usuario.objects.get(idusuario=payload["idusuario"])
            inmobiliaria = Inmobiliaria.objects.get(idinmobiliaria=payload["idinmobiliaria"])
            request.user = user
            request.inmobiliaria = inmobiliaria
        except jwt.ExpiredSignatureError:
            return Response({"error": "Sesión expirada"}, status=401)
        except jwt.InvalidTokenError:
            return Response({"error": "Token inválido"}, status=401)
        except Usuario.DoesNotExist:
            return Response({"error": "Usuario no encontrado"}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper


# Listar todos los usuarios activos
@api_view(['GET'])
def listUsuarios(request):
    usuarios = Usuario.objects.filter(estado=1)
    serializer = UsuarioSerializer(usuarios, many=True)
    return Response(serializer.data)


# Crear usuario
@api_view(['POST'])
def registerUsuario(request):
    data = {
    'correo': request.data.get('correo'),
    'password': make_password(request.data.get('password')),
    'nombre': request.data.get('nombre'),
    'estado': 1
}
    serializer = UsuarioSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Obtener usuario por id
@api_view(['GET'])
def listUsuarioId(request, idusuario):
    usuario = Usuario.objects.filter(idusuario=idusuario, estado=1).first()
    if usuario:
        serializer = UsuarioSerializer(usuario)
        return Response(serializer.data)
    return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)


# Actualizar usuario (PUT - todo el objeto)
@api_view(['PUT'])
def updateUsuario(request, idusuario):
    try:
        usuario = Usuario.objects.get(idusuario=idusuario)
    except Usuario.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    serializer = UsuarioSerializer(usuario, data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=200)
    return Response(serializer.errors, status=400)


# Eliminar usuario (soft delete → estado = 0)
@api_view(['PUT'])
def deleteUsuario(request, idusuario):
    try:
        usuario = Usuario.objects.get(idusuario=idusuario)
    except Usuario.DoesNotExist:
        return Response({'error': 'Usuario no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    usuario.estado = 0
    usuario.save()
    return Response({'message': 'Usuario desactivado correctamente'}, status=status.HTTP_200_OK)

@api_view(['POST'])
def register_inmobiliaria_usuario(request):
    usuario_data = {
        'correo': request.data.get('correo'),
        'password': make_password(request.data.get('password')),
        'nombre': request.data.get('nombre'),
        'estado': 1
    }
    usuario_serializer = UsuarioSerializer(data=usuario_data)
    if usuario_serializer.is_valid():
        usuario = usuario_serializer.save()

        inmobiliaria_data = {
            'nombreinmobiliaria': request.data.get('nombreinmobiliaria'),
            'facebook': request.data.get('facebook'),
            'whatsapp': request.data.get('whatsapp'),
            'pagina': request.data.get('pagina'),
            'estado': 1,
            'idusuario': usuario,
            'descripcion': request.data.get('descripcion'),
        }
        inmo_serializer = InmobiliariaSerializer(data=inmobiliaria_data)
        if inmo_serializer.is_valid():
            inmo = inmo_serializer.save()
            return Response({
                "usuario": usuario_serializer.data,
                "inmobiliaria": inmo_serializer.data
            }, status=status.HTTP_201_CREATED)

        return Response(inmo_serializer.errors, status=400)
    return Response(usuario_serializer.errors, status=400)


@api_view(["POST"])
@permission_classes([AllowAny])
def login_usuario(request):
    serializer = LoginSerializer(data=request.data)
    if serializer.is_valid():
        usuario = serializer.validated_data["usuario"]
        refresh = RefreshToken.for_user(usuario)
        access = str(refresh.access_token)
        try:
            inmobiliaria = Inmobiliaria.objects.filter(idusuario=usuario).first()
        except Inmobiliaria.DoesNotExist:
            inmobiliaria = None

        return Response({
            "refresh": str(refresh),
            "access": access,
            "usuario": {
                "idusuario": usuario.idusuario,
                "correo": usuario.correo,
                "nombre": usuario.nombre,
            },
            "inmobiliaria": {
                "idinmobiliaria": inmobiliaria.idinmobiliaria if inmobiliaria else None,
                "nombreinmobiliaria": inmobiliaria.nombreinmobiliaria if inmobiliaria else None
            } if inmobiliaria else None
        }, status=status.HTTP_200_OK)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


def get_user_from_token(request):
    token = request.COOKIES.get("jwt")  # o desde headers Authorization
    if not token:
        return None, None

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None, None

    usuario = Usuario.objects.filter(idusuario=payload["idusuario"]).first()
    inmobiliaria = Inmobiliaria.objects.filter(idinmobiliaria=payload["idinmobiliaria"]).first()
    return usuario, inmobiliaria

@api_view(["POST"])
@permission_classes([AllowAny])
def refresh_token(request):
    token = request.data.get("refresh")
    if not token:
        return Response({"detail": "Token no proporcionado"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        validated_token = RefreshToken(token)
        access = str(validated_token.access_token)
        return Response({"access": access})
    except TokenError:
        return Response({"detail": "Token inválido"}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['GET'])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def mis_proyectos(request):
    try:
        usuario = request.user
        inmobiliaria = Inmobiliaria.objects.filter(idusuario=usuario).first()
        if not inmobiliaria:
            return Response({"detail": "No tiene inmobiliaria asociada"}, status=status.HTTP_403_FORBIDDEN)

        proyectos = Proyecto.objects.filter(idinmobiliaria=inmobiliaria.idinmobiliaria)
        serializer = ProyectoSerializer(proyectos, many=True)
        return Response(serializer.data)

    except Exception as e:
        return Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    
class CheckAuthView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            "detail": "Token válido",
            "idusuario": user.idusuario,
            "correo": user.correo,
            "nombre": user.nombre
        }, status=status.HTTP_200_OK)


@api_view(['POST'])
def logout(request):
    response = Response({"message": "Sesión cerrada"})
    response.delete_cookie("jwt")
    return response