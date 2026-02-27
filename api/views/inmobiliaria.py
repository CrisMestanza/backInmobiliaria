from rest_framework.decorators import api_view, permission_classes, authentication_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from ..serializers import InmobiliariaSerializer, PuntosSerializer, LoteSerializer, PuntosProyectoSerializer, InmobiliariaRegistroSerializer
from ..models import Inmobiliaria, Imagenes, Puntos, Lote, PuntosProyecto
from rest_framework import status
import json 
from django.db.models import Prefetch
from ..authentication import CustomJWTAuthentication
from ..throttling import RegisterRateThrottle
import sys
sys.stdout.reconfigure(encoding='utf-8')
@api_view(['GET'])
@permission_classes([AllowAny])
def list_inmobiliarias(request):
    if request.method == 'GET':
        inmobiliarias = Inmobiliaria.objects.all()
        serializer = InmobiliariaSerializer(inmobiliarias, many=True)
        return Response(serializer.data)

@api_view(['GET'])
@permission_classes([AllowAny])
def list_puntos(request, idlote):
    if request.method == 'GET':
        puntos = Puntos.objects.filter(idlote=idlote) 
        serializer = PuntosSerializer(puntos, many=True)
        return Response(serializer.data)

@api_view(['GET'])
@permission_classes([AllowAny])
def list_puntos_por_proyecto(request, idproyecto):
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
                queryset=Puntos.objects.only("idlote_id", "latitud", "longitud", "orden").order_by("orden"),
            )
        )
    )

    data = []
    for lote in lotes:
        data.append({
            "id": lote.idlote,
            "nombre": lote.nombre,
            "descripcion": lote.descripcion,
            "precio": lote.precio,
            "vendido": lote.vendido,
            "puntos": PuntosSerializer(lote.puntos_set.all(), many=True).data,
        })
    
    return Response(data)

@api_view(['GET'])
@permission_classes([AllowAny])
def list_puntosproyecto(request, idproyecto):
    if request.method == 'GET':
        puntos = PuntosProyecto.objects.filter(idproyecto=idproyecto) 
        serializer = PuntosProyectoSerializer(puntos, many=True)
        return Response(serializer.data)

@api_view(['POST'])
@permission_classes([AllowAny])
def validar_lote(request, idproyecto):
    puntos_proyecto = list(PuntosProyecto.objects.filter(idproyecto=idproyecto).values_list("latitud", "longitud"))
    puntos_lote = request.data.get("puntos", [])
    # usar shapely para validar
    from shapely.geometry import Polygon, Point
    poly_proyecto = Polygon(puntos_proyecto)
    poly_lote = Polygon([(float(p["latitud"]), float(p["longitud"])) for p in puntos_lote])
    valido = poly_proyecto.contains(poly_lote)
    return Response({"valido": valido})

@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([RegisterRateThrottle])
def registrar_inmobiliaria(request):
    serializer = InmobiliariaRegistroSerializer(data=request.data)
    if serializer.is_valid():
        inmobiliaria = serializer.save()
        return Response(InmobiliariaRegistroSerializer(inmobiliaria).data, status=201)
    print("❌ Errores:", serializer.errors)
    return Response(serializer.errors, status=400)

@api_view(['GET'])
@permission_classes([AllowAny])
def list_inmobiliarias_id(request, idlote):
    if request.method == 'GET':
        lote = Lote.objects.filter(idlote=idlote)
        serializer = LoteSerializer(lote, many=True)
        return Response(serializer.data)

@api_view(['GET'])
@permission_classes([AllowAny])
def getInmobiliaria(request, idinmobiliaria):
    inmobiliarias = Inmobiliaria.objects.filter(idinmobiliaria = idinmobiliaria)
    serializer = InmobiliariaSerializer(inmobiliarias, many=True)
    return Response(serializer.data)


@api_view(['PUT'])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def updateInmobiliaria(request, idinmobiliaria):
    try:
        inmobiliaria = Inmobiliaria.objects.get(idinmobiliaria=idinmobiliaria)
    except Inmobiliaria.DoesNotExist:
        return Response({'error': 'Inmobiliaria no encontrada'}, status=status.HTTP_404_NOT_FOUND)

    if inmobiliaria.idusuario_id != request.user.idusuario:
        return Response({'error': 'No tienes permisos para editar esta inmobiliaria'}, status=status.HTTP_403_FORBIDDEN)

    serializer = InmobiliariaSerializer(inmobiliaria, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=200)
    return Response(serializer.errors, status=400)

@api_view(['PUT'])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def deleteInmobiliaria(request, idinmobiliaria):
    try:
        inmobiliaria = Inmobiliaria.objects.get(idinmobiliaria=idinmobiliaria)
    except Inmobiliaria.DoesNotExist:
        return Response({'error': 'Inmobiliaria no encontrada'}, status=status.HTTP_404_NOT_FOUND)

    if inmobiliaria.idusuario_id != request.user.idusuario:
        return Response({'error': 'No tienes permisos para eliminar esta inmobiliaria'}, status=status.HTTP_403_FORBIDDEN)

    inmobiliaria.estado = 0
    inmobiliaria.save()
    return Response({'message': 'Inmobiliaria desactivada correctamente'}, status=status.HTTP_200_OK)
