from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from ..serializers import IconosSerializer
from ..models import Iconos
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.decorators import authentication_classes
from ..authentication import CustomJWTAuthentication
from rest_framework.permissions import IsAuthenticated
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
    data = {
        'nombreicono': request.data.get('nombreicono'),
        'longitud': request.data.get('longitud'),
        'latitud': request.data.get('latitud'),
        'idproyecto': request.data.get('idproyecto'),
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

    serializer = IconosSerializer(icono, data=request.data)
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
