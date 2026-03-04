from django.db.models import Prefetch
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
from api.models import Inmobiliaria, Lote, Puntos, PuntosProyecto
from api.serializers import (
    InmobiliariaRegistroSerializer,
    InmobiliariaSerializer,
    LoteSerializer,
    PuntosProyectoSerializer,
    PuntosSerializer,
)
from api.throttling import RegisterRateThrottle


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
    serializer = InmobiliariaRegistroSerializer(data=request.data)
    if serializer.is_valid():
        inmobiliaria = serializer.save()
        return Response(InmobiliariaRegistroSerializer(inmobiliaria).data, status=201)
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
    return Response(
        {"message": "Inmobiliaria desactivada correctamente"}, status=status.HTTP_200_OK
    )
