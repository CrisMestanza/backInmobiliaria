from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from ..serializers import IconosSerializer
from ..models import Iconos
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.decorators import authentication_classes
from ..authentication import CustomJWTAuthentication
from rest_framework.permissions import IsAuthenticated
from ..security_uploads import build_secure_image_name, validate_uploaded_image
from .permissions import user_inmobiliaria_id
import sys
sys.stdout.reconfigure(encoding='utf-8')
# Listar iconos activos
@api_view(['GET'])
@permission_classes([AllowAny])
def listIconos(request):
    iconos = Iconos.objects.filter(estado=1)
    serializer = IconosSerializer(iconos, many=True)
    return Response(serializer.data)


# Crear icono
@api_view(['POST'])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def registerIcono(request):
    imagen = request.FILES.get('imagen')
    if imagen is None:
        return Response({"error": "La imagen es requerida"}, status=status.HTTP_400_BAD_REQUEST)

    validate_uploaded_image(imagen)
    imagen.name = build_secure_image_name(
        inmobiliaria_id=user_inmobiliaria_id(request.user),
        proyecto_id=request.data.get('idproyecto', 'global'),
        image_type="icono",
        original_name=imagen.name,
    )

    data = {
        'nombre': request.data.get('nombre'),
        'imagen': imagen,
        'estado': 1
    }
    serializer = IconosSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# Obtener icono por id
@api_view(['GET'])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def listIconoId(request, idiconos):
    icono = Iconos.objects.filter(idiconos=idiconos, estado=1).first()
    if icono:
        serializer = IconosSerializer(icono)
        return Response(serializer.data)
    return Response({'error': 'Icono no encontrado'}, status=status.HTTP_404_NOT_FOUND)


# Actualizar icono (PUT - todo el objeto)
@api_view(['PUT'])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def updateIcono(request, idiconos):
    try:
        icono = Iconos.objects.get(idiconos=idiconos)
    except Iconos.DoesNotExist:
        return Response({'error': 'Icono no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    payload = request.data.copy()
    imagen = request.FILES.get('imagen')
    if imagen:
        validate_uploaded_image(imagen)
        imagen.name = build_secure_image_name(
            inmobiliaria_id=user_inmobiliaria_id(request.user),
            proyecto_id=request.data.get('idproyecto', 'global'),
            image_type="icono-update",
            original_name=imagen.name,
        )
        payload['imagen'] = imagen

    serializer = IconosSerializer(icono, data=payload, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=200)
    return Response(serializer.errors, status=400)


# Eliminar icono (soft delete → estado = 0)
@api_view(['PUT'])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def deleteIcono(request, idiconos):
    try:
        icono = Iconos.objects.get(idiconos=idiconos)
    except Iconos.DoesNotExist:
        return Response({'error': 'Icono no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    icono.estado = 0
    icono.save()
    return Response({'message': 'Icono desactivado correctamente'}, status=status.HTTP_200_OK)
