from django.db import transaction
from django.db.models import Prefetch
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.authentication import CustomJWTAuthentication
from api.dashboard_cache import invalidate_dashboard_cache_for_inmobiliaria
from api.models import Espacio, Proyecto, PuntosEspacio, TipoEspacio
from api.serializers import EspacioMapaSerializer, EspacioSerializer, TipoEspacioSerializer
from api.validation_utils import parse_polygon_points, polygon_area_m2
from api.views.permissions import is_project_owned_by_user


def _espacio_centroid(points: list[dict[str, float]]) -> tuple[float | None, float | None]:
    if not points:
        return None, None
    if len(points) < 3:
        return points[0]["latitud"], points[0]["longitud"]

    coords = [(p["longitud"], p["latitud"]) for p in points]
    area2 = 0.0
    cx = 0.0
    cy = 0.0

    for i in range(len(coords)):
        x1, y1 = coords[i]
        x2, y2 = coords[(i + 1) % len(coords)]
        cross = x1 * y2 - x2 * y1
        area2 += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross

    if abs(area2) < 1e-12:
        avg_lat = sum(p["latitud"] for p in points) / len(points)
        avg_lng = sum(p["longitud"] for p in points) / len(points)
        return avg_lat, avg_lng

    area = area2 / 2.0
    return cy / (6.0 * area), cx / (6.0 * area)


def _validate_espacio_points(raw_points):
    points = parse_polygon_points(raw_points)
    if len(points) < 3:
        return None, Response(
            {"puntos": ["El espacio debe tener al menos 3 puntos válidos."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    area_m2 = polygon_area_m2(points)
    if area_m2 <= 0:
        return None, Response(
            {"puntos": ["No se pudo calcular un polígono válido para el espacio."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return points, None


@api_view(["GET"])
@permission_classes([AllowAny])
def list_tipos_espacio(_request):
    tipos = TipoEspacio.objects.filter(estado=1).order_by("orden_visual", "nombre")
    return Response(TipoEspacioSerializer(tipos, many=True).data)


@api_view(["GET"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([AllowAny])
def list_espacios_proyecto(request, idproyecto):
    include_hidden = str(request.query_params.get("include_hidden", "0")).lower() in {
        "1",
        "true",
        "yes",
    }
    filters = {"idproyecto": idproyecto, "estado": 1}
    if include_hidden:
        if not request.user or not request.user.is_authenticated:
            return Response(
                {"error": "Debes iniciar sesión para ver todos los espacios."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        if not is_project_owned_by_user(idproyecto, request.user):
            return Response(
                {"error": "No tienes permisos para ver estos espacios."},
                status=status.HTTP_403_FORBIDDEN,
            )
    else:
        filters["visible_mapa"] = 1

    espacios = (
        Espacio.objects.filter(**filters)
        .select_related("idtipoespacio")
        .prefetch_related(
            Prefetch(
                "puntos",
                queryset=PuntosEspacio.objects.only(
                    "idespacio_id", "latitud", "longitud", "orden"
                ).order_by("orden"),
            )
        )
        .order_by("idtipoespacio__orden_visual", "nombre")
    )
    return Response(EspacioMapaSerializer(espacios, many=True).data)


@api_view(["POST"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def register_espacio(request):
    project_id = request.data.get("idproyecto")
    if not project_id or not is_project_owned_by_user(project_id, request.user):
        return Response(
            {"error": "No tienes permisos para crear espacios en este proyecto."},
            status=status.HTTP_403_FORBIDDEN,
        )

    puntos_raw = request.data.get("puntos", [])
    puntos_valid, puntos_error = _validate_espacio_points(puntos_raw)
    if puntos_error:
        return puntos_error

    centro_lat, centro_lng = _espacio_centroid(puntos_valid)
    area_m2 = polygon_area_m2(puntos_valid)
    data = {
        "idproyecto": project_id,
        "idtipoespacio": request.data.get("idtipoespacio"),
        "nombre": request.data.get("nombre"),
        "descripcion": request.data.get("descripcion"),
        "area_m2": round(area_m2, 2),
        "centro_lat": centro_lat,
        "centro_lng": centro_lng,
        "visible_mapa": request.data.get("visible_mapa", 1),
        "destacado": request.data.get("destacado", 0),
        "estado": 1,
    }
    serializer = EspacioSerializer(data=data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        espacio = serializer.save()
        PuntosEspacio.objects.bulk_create(
            [
                PuntosEspacio(
                    idespacio=espacio,
                    latitud=p["latitud"],
                    longitud=p["longitud"],
                    orden=idx + 1,
                )
                for idx, p in enumerate(puntos_valid)
            ],
            batch_size=500,
        )

    proyecto = Proyecto.objects.filter(idproyecto=project_id).only("idinmobiliaria_id").first()
    invalidate_dashboard_cache_for_inmobiliaria(
        getattr(proyecto, "idinmobiliaria_id", None)
    )
    return Response(EspacioSerializer(espacio).data, status=status.HTTP_201_CREATED)


@api_view(["PUT"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def update_espacio(request, idespacio):
    espacio = (
        Espacio.objects.select_related("idproyecto")
        .filter(idespacio=idespacio)
        .first()
    )
    if not espacio:
        return Response({"error": "Espacio no encontrado"}, status=status.HTTP_404_NOT_FOUND)
    if not is_project_owned_by_user(espacio.idproyecto_id, request.user):
        return Response(
            {"error": "No tienes permisos para editar este espacio."},
            status=status.HTTP_403_FORBIDDEN,
        )

    request_data = request.data.copy()
    if "puntos" in request.data:
        puntos_valid, puntos_error = _validate_espacio_points(request.data.get("puntos", []))
        if puntos_error:
            return puntos_error
        centro_lat, centro_lng = _espacio_centroid(puntos_valid)
        request_data["area_m2"] = round(polygon_area_m2(puntos_valid), 2)
        request_data["centro_lat"] = centro_lat
        request_data["centro_lng"] = centro_lng
    else:
        puntos_valid = None
    request_data.pop("puntos", None)

    serializer = EspacioSerializer(espacio, data=request_data, partial=True)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        espacio = serializer.save()
        if puntos_valid is not None:
            PuntosEspacio.objects.filter(idespacio=espacio.idespacio).delete()
            PuntosEspacio.objects.bulk_create(
                [
                    PuntosEspacio(
                        idespacio=espacio,
                        latitud=p["latitud"],
                        longitud=p["longitud"],
                        orden=idx + 1,
                    )
                    for idx, p in enumerate(puntos_valid)
                ],
                batch_size=500,
            )

    invalidate_dashboard_cache_for_inmobiliaria(
        getattr(espacio.idproyecto, "idinmobiliaria_id", None)
    )
    return Response(EspacioSerializer(espacio).data)


@api_view(["DELETE"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def delete_espacio(request, idespacio):
    espacio = (
        Espacio.objects.select_related("idproyecto")
        .filter(idespacio=idespacio)
        .first()
    )
    if not espacio:
        return Response({"error": "Espacio no encontrado"}, status=status.HTTP_404_NOT_FOUND)
    if not is_project_owned_by_user(espacio.idproyecto_id, request.user):
        return Response(
            {"error": "No tienes permisos para eliminar este espacio."},
            status=status.HTTP_403_FORBIDDEN,
        )

    inmo_id = getattr(espacio.idproyecto, "idinmobiliaria_id", None)
    espacio.delete()
    invalidate_dashboard_cache_for_inmobiliaria(inmo_id)
    return Response({"message": "Espacio eliminado correctamente."})
