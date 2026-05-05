import json
import os
from io import BytesIO
from typing import Any, TypedDict, cast

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Prefetch, Q
from django.views.decorators.cache import cache_page
from PIL import Image, ImageOps
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
from api.dashboard_cache import invalidate_dashboard_cache_for_inmobiliaria
from api.file_cleanup import delete_files_and_empty_dirs
from api.models import (
    ClickProyectos,
    ClicksContactos,
    Espacio,
    IconoProyecto,
    Imagenes,
    ImagenesProyecto,
    Inmobiliaria,
    Lote,
    Proyecto,
    Puntos,
    PuntosEspacio,
    PuntosProyecto,
)
from api.serializers import (
    EspacioMapaSerializer,
    ImagenesProyectoMapaSerializer,
    IconoProyectoSerializer,
    InmobiliariaSerializer,
    LoteMapaDetalleSerializer,
    ProyectoDetalleMapaSerializer,
    ProyectoMapaDetalleSerializer,
    ProyectoMapaMarkerSerializer,
    ProyectoMapaSerializer,
    ProyectoSerializer,
    PuntosProyectoMapaSerializer,
)
from api.views.permissions import IsOwnerOfProyecto, user_inmobiliaria_id
from api.security_uploads import build_unique_image_name, validate_uploaded_image
from api.validation_utils import parse_polygon_points, polygon_area_m2

PROYECTO_MAP_ONLY_FIELDS = (
    "idproyecto",
    "nombreproyecto",
    "latitud",
    "longitud",
    "idinmobiliaria_id",
    "idtipoinmobiliaria_id",
    "estado",
    "descripcion",
    "precio",
    "area_total_m2",
    "dormitorios",
    "banos",
    "cuartos",
    "titulo_propiedad",
    "cochera",
    "cocina",
    "sala",
    "patio",
    "jardin",
    "terraza",
    "azotea",
    "ancho",
    "largo",
    "agua",
    "desague",
    "luz",
    "alumbrado_publico",
    "postes_luz",
    "veredas",
    "financing_config",
)
from api.throttling import PublicMapRateThrottle

PROYECTO_MAP_MARKER_FIELDS = (
    "idproyecto",
    "nombreproyecto",
    "latitud",
    "longitud",
    "estado",
    "idtipoinmobiliaria_id",
    "publico_mapa",
    "financing_config",
)

LOTE_MAP_DETAIL_FIELDS = (
    "idlote",
    "nombre",
    "descripcion",
    "estado",
    "latitud",
    "longitud",
    "idtipoinmobiliaria_id",
    "precio",
    "vendido",
    "area_total_m2",
    "dormitorios",
    "banos",
    "cuartos",
    "titulo_propiedad",
    "cochera",
    "cocina",
    "sala",
    "patio",
    "jardin",
    "terraza",
    "azotea",
    "ancho",
    "largo",
    "idproyecto_id",
)


class ProjectPoint(TypedDict):
    latitud: float
    longitud: float


def _project_centroid(points: list[ProjectPoint]) -> tuple[float | None, float | None]:
    if not points:
        return None, None
    if len(points) < 3:
        first = points[0]
        return first["latitud"], first["longitud"]

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


def _ensure_activated_user(request):
    if not getattr(request.user, "is_active", False) or getattr(request.user, "estado", 0) != 1:
        return Response(
            {"error": "Primero debes activar tu cuenta para poder crear lotes o proyectos."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _parse_json_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _parse_optional_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "si", "sí", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    return None


PROYECTO_UTILITY_FIELDS = (
    "agua",
    "desague",
    "luz",
    "alumbrado_publico",
    "postes_luz",
    "veredas",
)


def _parse_int_list(value: Any) -> list[int]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []
    result: list[int] = []
    for item in value:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def _validate_project_points(
    puntos_data: list[dict[str, Any]],
) -> tuple[list[ProjectPoint], Response | None]:
    points = cast(list[ProjectPoint], parse_polygon_points(puntos_data))
    if len(points) < 3:
        return [], Response(
            {"puntos": ["El proyecto debe tener al menos 3 puntos válidos."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    max_area_m2 = float(getattr(settings, "PROJECT_MAX_POLYGON_AREA_M2", 5000000))
    area_m2 = polygon_area_m2(points)
    if area_m2 <= 0:
        return [], Response(
            {"puntos": ["No se pudo calcular un polígono válido para el proyecto."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if area_m2 > max_area_m2:
        return [], Response(
            {
                "puntos": [
                    "El área del proyecto excede el límite permitido. Ajusta el trazado."
                ]
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return points, None


PROJECT_360_WEB_SIZE = (4096, 2048)
PROJECT_360_PREVIEW_SIZE = (1024, 512)
PROJECT_360_QUALITY = 78


def _project_360_base_dir(proyecto: Proyecto) -> str:
    inmo_id = getattr(proyecto.idinmobiliaria, "idinmobiliaria", None) or "sin-inmo"
    return f"inmobiliarias/{inmo_id}/proyectos/{proyecto.idproyecto}/dron"


def _project_360_relative_url(base_dir: str, filename: str) -> str:
    return f"/media/{base_dir}/{filename}"


def _project_360_config_relative_url(base_dir: str) -> str:
    return _project_360_relative_url(base_dir, "360_config.json")


def _project_360_preview_url(value: str | None) -> str | None:
    if not value:
        return None
    root, ext = os.path.splitext(str(value))
    return f"{root}_preview{ext or '.jpg'}"


def _render_project_360_variant(uploaded_file, size: tuple[int, int]) -> bytes:
    uploaded_file.seek(0)
    with Image.open(uploaded_file) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB",):
            img = img.convert("RGB")
        rendered = Image.new("RGB", size, (8, 12, 18))
        fitted = ImageOps.contain(img, size, method=Image.Resampling.LANCZOS)
        offset = (
            (size[0] - fitted.width) // 2,
            (size[1] - fitted.height) // 2,
        )
        rendered.paste(fitted, offset)
        output = BytesIO()
        rendered.save(
            output,
            format="JPEG",
            quality=PROJECT_360_QUALITY,
            optimize=True,
            progressive=True,
        )
        return output.getvalue()


def _save_project_360_variants(proyecto: Proyecto, uploaded_file) -> tuple[str, str]:
    base_dir = _project_360_base_dir(proyecto)
    web_rel = _project_360_relative_url(base_dir, "360_web.jpg")
    preview_rel = _project_360_relative_url(base_dir, "360_web_preview.jpg")
    web_storage_path = web_rel.replace("/media/", "", 1)
    preview_storage_path = preview_rel.replace("/media/", "", 1)

    web_bytes = _render_project_360_variant(uploaded_file, PROJECT_360_WEB_SIZE)
    preview_bytes = _render_project_360_variant(uploaded_file, PROJECT_360_PREVIEW_SIZE)

    if default_storage.exists(web_storage_path):
        default_storage.delete(web_storage_path)
    if default_storage.exists(preview_storage_path):
        default_storage.delete(preview_storage_path)

    default_storage.save(web_storage_path, ContentFile(web_bytes))
    default_storage.save(preview_storage_path, ContentFile(preview_bytes))
    return web_rel, preview_rel


def _save_project_360_config(proyecto: Proyecto, config_payload: dict[str, Any] | None) -> str | None:
    proyecto.viewer_360_config = json.dumps(config_payload, ensure_ascii=False) if config_payload else None
    if not proyecto.imagen_360_url:
        return None
    base_dir = _project_360_base_dir(proyecto)
    rel_url = _project_360_config_relative_url(base_dir)
    storage_path = rel_url.replace("/media/", "", 1)
    if not config_payload:
        if default_storage.exists(storage_path):
            default_storage.delete(storage_path)
        return rel_url
    payload = json.dumps(config_payload, ensure_ascii=False)
    if default_storage.exists(storage_path):
        default_storage.delete(storage_path)
    default_storage.save(storage_path, ContentFile(payload.encode("utf-8")))
    return rel_url


def _load_project_360_config(proyecto: Proyecto) -> dict[str, Any] | None:
    if getattr(proyecto, "viewer_360_config", None):
        try:
            return json.loads(proyecto.viewer_360_config)
        except Exception:
            pass
    if not proyecto.imagen_360_url:
        return None
    base_dir = _project_360_base_dir(proyecto)
    rel_url = _project_360_config_relative_url(base_dir)
    storage_path = rel_url.replace("/media/", "", 1)
    if not default_storage.exists(storage_path):
        return None
    try:
        with default_storage.open(storage_path, "r") as handle:
            return json.load(handle)
    except Exception:
        return None


def _collect_project_360_upload(request):
    for key in ("imagen_360", "imagen360", "imagen_360_file", "panorama_360"):
        if request.FILES.get(key):
            return request.FILES.get(key)
    return None


def _normalize_json_payload(raw_value, field_name):
    if raw_value in (None, "", []):
        return None, None
    if isinstance(raw_value, (dict, list)):
        return json.dumps(raw_value, ensure_ascii=False), None
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return None, Response(
            {field_name: ["Debe ser un JSON válido."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not isinstance(parsed, (dict, list)):
        return None, Response(
            {field_name: ["Debe ser un objeto o lista JSON válido."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return json.dumps(parsed, ensure_ascii=False), None


@cache_page(60)
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([PublicMapRateThrottle])
def list_proyectos_mapa(request):
    """
    Endpoint ligero para marcadores del mapa.
    Retorna solo campos mínimos y lat/lng centrados según puntos.
    """
    tipo = request.GET.get("tipo")
    rango = request.GET.get("rango")
    inmo = request.GET.get("inmo")

    proyectos = (
        Proyecto.objects.filter(estado=1, puntos__isnull=False)
        .distinct()
        .only(*PROYECTO_MAP_MARKER_FIELDS)
    )

    if tipo:
        proyectos = proyectos.filter(idtipoinmobiliaria=tipo)
    if inmo:
        proyectos = proyectos.filter(idinmobiliaria=inmo)
    else:
        proyectos = proyectos.filter(Q(publico_mapa=1) | Q(publico_mapa__isnull=True))
    if rango:
        try:
            min_p, max_p = map(float, str(rango).split("-"))
            proyectos = proyectos.filter(
                lote__precio__range=(min_p, max_p),
                lote__vendido=0,
            ).distinct()
        except (TypeError, ValueError):
            pass

    serializer = ProyectoMapaMarkerSerializer(proyectos, many=True)
    return Response(serializer.data)


@cache_page(30)
@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([PublicMapRateThrottle])
def mapa_proyecto_detalle(_request, idproyecto):
    """
    Endpoint agregado: devuelve en una sola llamada
    proyecto + inmobiliaria + puntos + lotes(+puntos) + iconos.
    """
    proyecto = (
        Proyecto.objects.filter(idproyecto=idproyecto, estado=1)
        .select_related("idinmobiliaria")
        .prefetch_related(
            Prefetch(
                "puntos",
                queryset=PuntosProyecto.objects.only(
                    "idproyecto_id", "latitud", "longitud", "orden"
                ).order_by("orden"),
            ),
            Prefetch(
                "lote_set",
                queryset=Lote.objects.only(*LOTE_MAP_DETAIL_FIELDS).prefetch_related(
                    Prefetch(
                        "puntos_set",
                        queryset=Puntos.objects.only(
                            "idlote_id", "latitud", "longitud", "orden"
                        ).order_by("orden"),
                    )
                ),
            ),
            Prefetch(
                "iconos_proyecto",
                queryset=IconoProyecto.objects.filter(estado=1)
                .select_related("idicono")
                .only(
                    "idiconoproyecto",
                    "idproyecto_id",
                    "idicono_id",
                    "latitud",
                    "longitud",
                    "estado",
                    "idicono__idiconos",
                    "idicono__nombre",
                    "idicono__imagen",
                    "idicono__estado",
                ),
            ),
            Prefetch(
                "espacios",
                queryset=Espacio.objects.filter(estado=1, visible_mapa=1)
                .select_related("idtipoespacio")
                .prefetch_related(
                    Prefetch(
                        "puntos",
                        queryset=PuntosEspacio.objects.only(
                            "idespacio_id", "latitud", "longitud", "orden"
                        ).order_by("orden"),
                    )
                ),
            ),
            Prefetch(
                "imagenesproyecto_set",
                queryset=ImagenesProyecto.objects.only(
                    "idimagenesp",
                    "imagenproyecto",
                    "idproyecto_id",
                ),
            ),
        )
        .first()
    )

    if not proyecto:
        return Response(
            {"error": "Proyecto no encontrado"}, status=status.HTTP_404_NOT_FOUND
        )

    return Response(
        {
            "proyecto": ProyectoMapaDetalleSerializer(proyecto).data,
            "inmobiliaria": InmobiliariaSerializer(proyecto.idinmobiliaria).data
            if proyecto.idinmobiliaria
            else None,
            "puntos": PuntosProyectoMapaSerializer(
                getattr(proyecto, "puntos").all(), many=True
            ).data,
            "lotes": LoteMapaDetalleSerializer(
                getattr(proyecto, "lote_set").all(), many=True
            ).data,
            "iconos": IconoProyectoSerializer(
                getattr(proyecto, "iconos_proyecto").all(), many=True
            ).data,
            "espacios": EspacioMapaSerializer(
                getattr(proyecto, "espacios").all(), many=True
            ).data,
            "imagenes_proyecto": ImagenesProyectoMapaSerializer(
                getattr(proyecto, "imagenesproyecto_set").all(), many=True
            ).data,
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
@throttle_classes([PublicMapRateThrottle])
def mapa_proyecto_share(_request, idproyecto):
    """
    Endpoint rápido para compartir proyecto:
    proyecto + inmobiliaria + puntos (sin lotes).
    """
    proyecto = (
        Proyecto.objects.filter(idproyecto=idproyecto, estado=1)
        .select_related("idinmobiliaria")
        .prefetch_related(
            Prefetch(
                "puntos",
                queryset=PuntosProyecto.objects.only(
                    "idproyecto_id", "latitud", "longitud", "orden"
                ).order_by("orden"),
            ),
            Prefetch(
                "espacios",
                queryset=Espacio.objects.filter(estado=1, visible_mapa=1)
                .select_related("idtipoespacio")
                .prefetch_related(
                    Prefetch(
                        "puntos",
                        queryset=PuntosEspacio.objects.only(
                            "idespacio_id", "latitud", "longitud", "orden"
                        ).order_by("orden"),
                    )
                )
                .order_by("idtipoespacio__orden_visual", "nombre"),
            ),
            Prefetch(
                "imagenesproyecto_set",
                queryset=ImagenesProyecto.objects.only(
                    "idimagenesp",
                    "imagenproyecto",
                    "idproyecto_id",
                ),
            ),
        )
        .first()
    )

    if not proyecto:
        return Response(
            {"error": "Proyecto no encontrado"}, status=status.HTTP_404_NOT_FOUND
        )

    return Response(
        {
            "proyecto": ProyectoMapaDetalleSerializer(proyecto).data,
            "inmobiliaria": InmobiliariaSerializer(proyecto.idinmobiliaria).data
            if proyecto.idinmobiliaria
            else None,
            "puntos": PuntosProyectoMapaSerializer(
                getattr(proyecto, "puntos").all(), many=True
            ).data,
            "espacios": EspacioMapaSerializer(
                getattr(proyecto, "espacios").all(), many=True
            ).data,
            "imagenes_proyecto": ImagenesProyectoMapaSerializer(
                getattr(proyecto, "imagenesproyecto_set").all(), many=True
            ).data,
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def listProyectos(_request):
    proyectos = (
        Proyecto.objects.filter(estado=1, puntos__isnull=False)
        .distinct()
        .only(*PROYECTO_MAP_ONLY_FIELDS)
        .prefetch_related(
            Prefetch(
                "iconos_proyecto",
                queryset=IconoProyecto.objects.filter(estado=1)
                .select_related("idicono")
                .only(
                    "idproyecto_id",
                    "latitud",
                    "longitud",
                    "idicono__nombre",
                    "idicono__imagen",
                ),
            )
        )
    )
    serializer = ProyectoMapaSerializer(proyectos, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def registerProyecto(request):
    blocked = _ensure_activated_user(request)
    if blocked:
        return blocked

    inmobiliaria_usuario = (
        Inmobiliaria.objects.filter(idusuario=request.user)
        .only("idinmobiliaria")
        .first()
    )
    if not inmobiliaria_usuario:
        return Response(
            {"error": "Usuario sin inmobiliaria asociada"},
            status=status.HTTP_403_FORBIDDEN,
        )

    idtipoinmobiliaria = request.data.get("idtipoinmobiliaria")
    if not idtipoinmobiliaria:
        return Response(
            {"idtipoinmobiliaria": ["El tipo de inmobiliaria es obligatorio."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    puntos_data_raw = _parse_json_list(request.data.get("puntos", []))
    puntos_data, puntos_error = _validate_project_points(puntos_data_raw)
    if puntos_error:
        return puntos_error
    centroid_lat, centroid_lng = _project_centroid(puntos_data)

    data = {
        "nombreproyecto": request.data.get("nombreproyecto"),
        "longitud": centroid_lng,
        "latitud": centroid_lat,
        "idinmobiliaria": inmobiliaria_usuario.idinmobiliaria,
        "descripcion": request.data.get("descripcion"),
        "idtipoinmobiliaria": idtipoinmobiliaria,
        "estado": 1,
        "dormitorios": request.data.get("dormitorios", 0),
        "banos": request.data.get("banos", 0),
        "cuartos": request.data.get("cuartos", 0),
        "titulo_propiedad": request.data.get("titulo_propiedad", 0),
        "cochera": request.data.get("cochera", 0),
        "cocina": request.data.get("cocina", 0),
        "sala": request.data.get("sala", 0),
        "patio": request.data.get("patio", 0),
        "jardin": request.data.get("jardin", 0),
        "terraza": request.data.get("terraza", 0),
        "azotea": request.data.get("azotea", 0),
        "precio": request.data.get("precio", 0),
        "area_total_m2": request.data.get("area_total_m2", 0),
        "ancho": request.data.get("ancho", 0),
        "largo": request.data.get("largo", 0),
        "pais": request.data.get("pais", ""),
        "bandera": request.data.get("bandera", ""),
        "moneda": request.data.get("moneda", ""),
        "agua": _parse_optional_bool(request.data.get("agua")),
        "desague": _parse_optional_bool(request.data.get("desague")),
        "luz": _parse_optional_bool(request.data.get("luz")),
        "alumbrado_publico": _parse_optional_bool(request.data.get("alumbrado_publico")),
        "postes_luz": _parse_optional_bool(request.data.get("postes_luz")),
        "veredas": _parse_optional_bool(request.data.get("veredas")),
        "dron_lat": request.data.get("dron_lat") or None,
        "dron_lng": request.data.get("dron_lng") or None,
        "dron_altitud": request.data.get("dron_altitud") or 80,
    }
    financing_config, financing_error = _normalize_json_payload(
        request.data.get("financing_config"),
        "financing_config",
    )
    if financing_error:
        return financing_error
    data["financing_config"] = financing_config

    serializer = ProyectoSerializer(data=data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        proyecto = cast(Proyecto, serializer.save())
        image360_preview_url = None
        image360_upload = _collect_project_360_upload(request)
        if image360_upload:
            validate_uploaded_image(image360_upload)
            web_url, image360_preview_url = _save_project_360_variants(
                proyecto,
                image360_upload,
            )
            proyecto.imagen_360_url = web_url
            proyecto.save(update_fields=["imagen_360_url"])

        puntos_bulk: list[PuntosProyecto] = []
        for idx, punto in enumerate(puntos_data):
            lat = punto.get("latitud", punto.get("lat"))
            lng = punto.get("longitud", punto.get("lng"))
            if lat is None or lng is None:
                continue
            puntos_bulk.append(
                PuntosProyecto(
                    idproyecto=proyecto,
                    latitud=lat,
                    longitud=lng,
                    orden=idx + 1,
                )
            )
        if puntos_bulk:
            PuntosProyecto.objects.bulk_create(puntos_bulk, batch_size=500)

        nuevas_imagenes: list[dict[str, Any]] = []
        for img in request.FILES.getlist("imagenes"):
            validate_uploaded_image(img)
            img.name = build_unique_image_name(img.name)
            imagen_obj = ImagenesProyecto.objects.create(
                idproyecto=proyecto, imagenproyecto=img
            )
            nuevas_imagenes.append(
                {
                    "idimagenesp": imagen_obj.idimagenesp,
                    "imagenproyecto": imagen_obj.imagenproyecto.url,
                    "idproyecto": proyecto.idproyecto,
                }
            )

    log_audit_event(
        request,
        "proyecto_create",
        status_code=status.HTTP_201_CREATED,
        success=True,
        target_resource="proyecto",
        target_id=proyecto.idproyecto,
        detail={"puntos": len(puntos_bulk), "imagenes": len(nuevas_imagenes)},
    )
    invalidate_dashboard_cache_for_inmobiliaria(inmobiliaria_usuario.idinmobiliaria)
    return Response(
        {
            "proyecto": serializer.data,
            "imagen_360_preview_url": image360_preview_url,
            "puntos_creados": len(puntos_bulk),
            "imagenes_creadas": nuevas_imagenes,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def listProyectoId(_request, idproyecto):
    proyecto = (
        Proyecto.objects.filter(idproyecto=idproyecto, estado=1)
        .only("idproyecto", "nombreproyecto")
        .prefetch_related(
            Prefetch(
                "puntos",
                queryset=PuntosProyecto.objects.only(
                    "idproyecto_id", "latitud", "longitud", "orden"
                ).order_by("orden"),
            ),
            Prefetch(
                "lote_set",
                queryset=Lote.objects.only(
                    "idlote",
                    "nombre",
                    "precio",
                    "vendido",
                    "latitud",
                    "longitud",
                    "idproyecto_id",
                ).prefetch_related(
                    Prefetch(
                        "puntos_set",
                        queryset=Puntos.objects.only(
                            "idlote_id", "latitud", "longitud", "orden"
                        ).order_by("orden"),
                    )
                ),
            ),
        )
        .first()
    )
    if not proyecto:
        return Response(
            {"error": "Proyecto no encontrado"}, status=status.HTTP_404_NOT_FOUND
        )

    serializer = ProyectoDetalleMapaSerializer(proyecto)
    return Response(serializer.data)


@api_view(["GET"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def getProyecto(request, idinmobiliaria):
    owner_inmo_id = user_inmobiliaria_id(request.user)
    if not owner_inmo_id or int(idinmobiliaria) != int(owner_inmo_id):
        return Response(
            {"error": "No tienes permisos para ver estos proyectos."},
            status=status.HTTP_403_FORBIDDEN,
        )

    proyecto = Proyecto.objects.filter(idinmobiliaria=idinmobiliaria)
    serializer = ProyectoSerializer(proyecto, many=True)
    return Response(serializer.data)


@api_view(["PUT"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated, IsOwnerOfProyecto])
def updateProyecto(request, idproyecto):
    try:
        proyecto = Proyecto.objects.get(idproyecto=idproyecto)
    except Proyecto.DoesNotExist:
        return Response(
            {"error": "Proyecto no encontrado"}, status=status.HTTP_404_NOT_FOUND
        )

    inmobiliaria_usuario = Inmobiliaria.objects.filter(idusuario=request.user).first()
    proyecto_inmobiliaria = proyecto.idinmobiliaria
    if (
        not inmobiliaria_usuario
        or not proyecto_inmobiliaria
        or proyecto_inmobiliaria.idinmobiliaria != inmobiliaria_usuario.idinmobiliaria
    ):
        return Response(
            {"error": "No tienes permisos para editar este proyecto."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if "idtipoinmobiliaria" in request.data and not request.data.get("idtipoinmobiliaria"):
        return Response(
            {"idtipoinmobiliaria": ["El tipo de inmobiliaria es obligatorio."]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    request_data = request.data.copy()
    if "financing_config" in request_data:
        financing_config, financing_error = _normalize_json_payload(
            request_data.get("financing_config"),
            "financing_config",
        )
        if financing_error:
            return financing_error
        request_data["financing_config"] = financing_config

    for utility_field in PROYECTO_UTILITY_FIELDS:
        if utility_field in request_data:
            request_data[utility_field] = _parse_optional_bool(
                request_data.get(utility_field)
            )

    serializer = ProyectoSerializer(proyecto, data=request_data, partial=True)
    if serializer.is_valid():
        with transaction.atomic():
            image_paths_to_delete: list[str] = []
            nuevas_imagenes: list[dict[str, Any]] = []
            serializer.save()
            image360_preview_url = None
            if "puntos" in request.data:
                puntos_data_raw = _parse_json_list(request.data.get("puntos", []))
                puntos_data, puntos_error = _validate_project_points(puntos_data_raw)
                if puntos_error:
                    transaction.set_rollback(True)
                    return puntos_error
                centroid_lat, centroid_lng = _project_centroid(puntos_data)
                proyecto.latitud = centroid_lat
                proyecto.longitud = centroid_lng
                proyecto.save(update_fields=["latitud", "longitud"])
                PuntosProyecto.objects.filter(idproyecto=proyecto.idproyecto).delete()
                PuntosProyecto.objects.bulk_create(
                    [
                        PuntosProyecto(
                            idproyecto=proyecto,
                            latitud=p["latitud"],
                            longitud=p["longitud"],
                            orden=idx + 1,
                        )
                        for idx, p in enumerate(puntos_data)
                    ],
                    batch_size=500,
                )
            if "imagenes_eliminadas" in request.data:
                ids_to_delete = _parse_int_list(request.data.get("imagenes_eliminadas", []))
                if ids_to_delete:
                    imagenes_qs = ImagenesProyecto.objects.filter(
                        idproyecto=proyecto.idproyecto,
                        idimagenesp__in=ids_to_delete,
                    )
                    image_paths_to_delete.extend(
                        str(path)
                        for path in imagenes_qs.values_list("imagenproyecto", flat=True)
                        if path
                    )
                    imagenes_qs.delete()
            for img in request.FILES.getlist("imagenes"):
                validate_uploaded_image(img)
                img.name = build_unique_image_name(img.name)
                imagen_obj = ImagenesProyecto.objects.create(
                    idproyecto=proyecto,
                    imagenproyecto=img,
                )
                nuevas_imagenes.append(
                    {
                        "idimagenesp": imagen_obj.idimagenesp,
                        "imagenproyecto": imagen_obj.imagenproyecto.url,
                        "idproyecto": proyecto.idproyecto,
                    }
                )
            image360_upload = _collect_project_360_upload(request)
            if image360_upload:
                validate_uploaded_image(image360_upload)
                if proyecto.imagen_360_url:
                    current_ext = os.path.splitext(str(proyecto.imagen_360_url))[1] or ".jpg"
                    current_preview = f"{os.path.splitext(str(proyecto.imagen_360_url))[0]}_preview{current_ext}"
                    image_paths_to_delete.extend(
                        [
                            str(proyecto.imagen_360_url),
                            current_preview,
                        ]
                    )
                web_url, image360_preview_url = _save_project_360_variants(
                    proyecto,
                    image360_upload,
                )
                proyecto.imagen_360_url = web_url
                if "dron_lat" in request.data:
                    proyecto.dron_lat = request.data.get("dron_lat") or None
                if "dron_lng" in request.data:
                    proyecto.dron_lng = request.data.get("dron_lng") or None
                if "dron_altitud" in request.data:
                    proyecto.dron_altitud = request.data.get("dron_altitud") or 80
                proyecto.save(
                    update_fields=[
                        "imagen_360_url",
                        "dron_lat",
                        "dron_lng",
                        "dron_altitud",
                    ]
                )
            if image_paths_to_delete:
                transaction.on_commit(
                    lambda paths=image_paths_to_delete: delete_files_and_empty_dirs(paths)
                )
        log_audit_event(
            request,
            "proyecto_update",
            status_code=status.HTTP_200_OK,
            success=True,
            target_resource="proyecto",
            target_id=idproyecto,
        )
        invalidate_dashboard_cache_for_inmobiliaria(
            getattr(proyecto_inmobiliaria, "idinmobiliaria", None)
        )
        return Response(
            {
                **serializer.data,
                "imagen_360_preview_url": image360_preview_url,
                "imagenes_creadas": nuevas_imagenes,
            },
            status=status.HTTP_200_OK,
        )
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PUT"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated, IsOwnerOfProyecto])
def proyecto_360_editor(request, idproyecto):
    try:
        proyecto = Proyecto.objects.select_related("idinmobiliaria").get(idproyecto=idproyecto)
    except Proyecto.DoesNotExist:
        return Response(
            {"error": "Proyecto no encontrado"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        return Response(
            {
                "idproyecto": proyecto.idproyecto,
                "imagen_360_url": proyecto.imagen_360_url,
                "imagen_360_preview_url": _project_360_preview_url(proyecto.imagen_360_url),
                "dron_lat": proyecto.dron_lat,
                "dron_lng": proyecto.dron_lng,
                "dron_altitud": proyecto.dron_altitud,
                "viewer_360_config": _load_project_360_config(proyecto),
            }
        )

    with transaction.atomic():
        image_paths_to_delete: list[str] = []
        image360_upload = _collect_project_360_upload(request)
        next_image_url = proyecto.imagen_360_url

        if image360_upload:
            validate_uploaded_image(image360_upload)
            if proyecto.imagen_360_url:
                current_ext = os.path.splitext(str(proyecto.imagen_360_url))[1] or ".jpg"
                current_preview = f"{os.path.splitext(str(proyecto.imagen_360_url))[0]}_preview{current_ext}"
                current_config = f"{os.path.splitext(str(proyecto.imagen_360_url))[0]}_config.json"
                image_paths_to_delete.extend(
                    [
                        str(proyecto.imagen_360_url),
                        current_preview,
                        current_config,
                    ]
                )
            web_url, _preview_url = _save_project_360_variants(proyecto, image360_upload)
            proyecto.imagen_360_url = web_url
            next_image_url = web_url

        if "dron_lat" in request.data:
            proyecto.dron_lat = request.data.get("dron_lat") or None
        if "dron_lng" in request.data:
            proyecto.dron_lng = request.data.get("dron_lng") or None
        if "dron_altitud" in request.data:
            proyecto.dron_altitud = request.data.get("dron_altitud") or 80

        viewer_config_raw = request.data.get("viewer_360_config")
        if viewer_config_raw is not None:
            try:
                viewer_config = json.loads(viewer_config_raw) if isinstance(viewer_config_raw, str) else viewer_config_raw
            except json.JSONDecodeError:
                return Response(
                    {"error": "viewer_360_config debe ser JSON válido"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            _save_project_360_config(proyecto, viewer_config if isinstance(viewer_config, dict) else None)

        proyecto.save(
            update_fields=["imagen_360_url", "dron_lat", "dron_lng", "dron_altitud", "viewer_360_config"]
        )

        if image_paths_to_delete:
            transaction.on_commit(
                lambda paths=image_paths_to_delete: delete_files_and_empty_dirs(paths)
            )

    return Response(
        {
            "idproyecto": proyecto.idproyecto,
            "imagen_360_url": next_image_url,
            "imagen_360_preview_url": _project_360_preview_url(next_image_url),
            "dron_lat": proyecto.dron_lat,
            "dron_lng": proyecto.dron_lng,
            "dron_altitud": proyecto.dron_altitud,
            "viewer_360_config": _load_project_360_config(proyecto),
        },
        status=status.HTTP_200_OK,
    )


@api_view(["DELETE"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def deleteProyecto(request, idproyecto):
    try:
        proyecto = Proyecto.objects.filter(idproyecto=idproyecto).first()
        if not proyecto:
            return Response(
                {"error": "Proyecto no encontrado."}, status=status.HTTP_404_NOT_FOUND
            )

        inmobiliaria_usuario = Inmobiliaria.objects.filter(
            idusuario=request.user
        ).first()
        if not inmobiliaria_usuario:
            return Response(
                {"error": "El usuario no tiene una inmobiliaria asociada."},
                status=status.HTTP_403_FORBIDDEN,
            )

        proyecto_inmobiliaria = proyecto.idinmobiliaria
        if (
            not proyecto_inmobiliaria
            or proyecto_inmobiliaria.idinmobiliaria != inmobiliaria_usuario.idinmobiliaria
        ):
            return Response(
                {"error": "No tienes permisos para eliminar este proyecto."},
                status=status.HTTP_403_FORBIDDEN,
            )

        with transaction.atomic():
            imagenes_lote_paths = list(
                Imagenes.objects.filter(idlote__idproyecto=idproyecto).values_list(
                    "imagen", flat=True
                )
            )
            imagenes_proyecto_paths = list(
                ImagenesProyecto.objects.filter(idproyecto=idproyecto).values_list(
                    "imagenproyecto", flat=True
                )
            )
            file_paths = [
                str(path)
                for path in (imagenes_lote_paths + imagenes_proyecto_paths)
                if path
            ]
            if proyecto.imagen_360_url:
                file_paths.extend(
                    [
                        str(proyecto.imagen_360_url),
                        _project_360_preview_url(proyecto.imagen_360_url),
                        f"{os.path.splitext(str(proyecto.imagen_360_url))[0]}_config.json",
                    ]
                )

            # 🔹 Eliminar primero relaciones dependientes
            ClickProyectos.objects.filter(idproyecto=idproyecto).delete()
            ClicksContactos.objects.filter(idproyecto=idproyecto).delete()
            Puntos.objects.filter(idlote__idproyecto=idproyecto).delete()
            Imagenes.objects.filter(idlote__idproyecto=idproyecto).delete()
            Lote.objects.filter(idproyecto=idproyecto).delete()
            ImagenesProyecto.objects.filter(idproyecto=idproyecto).delete()
            PuntosProyecto.objects.filter(idproyecto=idproyecto).delete()
            proyecto.delete()
            transaction.on_commit(lambda: delete_files_and_empty_dirs(file_paths))

        log_audit_event(
            request,
            "proyecto_delete",
            status_code=status.HTTP_200_OK,
            success=True,
            target_resource="proyecto",
            target_id=idproyecto,
        )
        invalidate_dashboard_cache_for_inmobiliaria(
            getattr(proyecto_inmobiliaria, "idinmobiliaria", None)
        )
        return Response(
            {"message": "Proyecto y todas sus relaciones eliminadas correctamente."},
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        log_audit_event(
            request,
            "proyecto_delete_failed",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            success=False,
            target_resource="proyecto",
            target_id=idproyecto,
            detail=str(e),
        )
        return Response(
            {"error": f"Ocurrió un error al eliminar el proyecto: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def tipoProyecto(_request, idtipoinmobiliaria):
    tipo = (
        Proyecto.objects.filter(
            estado=1,
            idtipoinmobiliaria=idtipoinmobiliaria,
            puntos__isnull=False,
        )
        .distinct()
        .only(*PROYECTO_MAP_ONLY_FIELDS)
        .prefetch_related(
            Prefetch(
                "iconos_proyecto",
                queryset=IconoProyecto.objects.filter(estado=1)
                .select_related("idicono")
                .only(
                    "idproyecto_id",
                    "latitud",
                    "longitud",
                    "idicono__nombre",
                    "idicono__imagen",
                ),
            )
        )
    )
    serializer = ProyectoMapaSerializer(tipo, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def listProyectosInmobiliaria(_request, idinmobiliaria):
    proyectos = Proyecto.objects.filter(
        idinmobiliaria=idinmobiliaria,
        estado=1,
        puntos__isnull=False,
    ).distinct()
    serializer = ProyectoSerializer(proyectos, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def proyectos_filtrados(request):
    tipo = request.GET.get("tipo")  # idtipoinmobiliaria
    rango = request.GET.get("rango")  # 15001-35000
    inmo = request.GET.get("inmo")  # opcional

    proyectos = (
        Proyecto.objects.filter(estado=1, puntos__isnull=False)
        .distinct()
        .only(*PROYECTO_MAP_ONLY_FIELDS)
        .prefetch_related(
            Prefetch(
                "iconos_proyecto",
                queryset=IconoProyecto.objects.filter(estado=1)
                .select_related("idicono")
                .only(
                    "idproyecto_id",
                    "latitud",
                    "longitud",
                    "idicono__nombre",
                    "idicono__imagen",
                ),
            )
        )
    )

    if tipo:
        proyectos = proyectos.filter(idtipoinmobiliaria=tipo)

    if inmo:
        proyectos = proyectos.filter(idinmobiliaria=inmo)

    if rango:
        try:
            min_p, max_p = map(float, rango.split("-"))
            proyectos = proyectos.filter(lote__precio__range=(min_p, max_p)).distinct()
        except ValueError:
            pass

    serializer = ProyectoMapaSerializer(proyectos, many=True)
    return Response(serializer.data)
