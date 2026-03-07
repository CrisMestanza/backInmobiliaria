import json

from django.conf import settings
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
from api.audit import log_audit_event
from api.models import (
    ClickProyectos,
    ClicksContactos,
    IconoProyecto,
    Imagenes,
    ImagenesProyecto,
    Inmobiliaria,
    Lote,
    Proyecto,
    Puntos,
    PuntosProyecto,
)
from api.serializers import (
    ProyectoDetalleMapaSerializer,
    ProyectoMapaSerializer,
    ProyectoSerializer,
)
from api.views.permissions import IsOwnerOfProyecto, user_inmobiliaria_id
from api.security_uploads import build_secure_image_name, validate_uploaded_image
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
)


def _ensure_activated_user(request):
    if not getattr(request.user, "is_active", False) or getattr(request.user, "estado", 0) != 1:
        return Response(
            {"error": "Primero debes activar tu cuenta para poder crear lotes o proyectos."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _parse_json_list(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return value if isinstance(value, list) else []


def _validate_project_points(puntos_data):
    points = parse_polygon_points(puntos_data)
    if len(points) < 3:
        return None, Response(
            {"puntos": ["El proyecto debe tener al menos 3 puntos válidos."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    max_area_m2 = float(getattr(settings, "PROJECT_MAX_POLYGON_AREA_M2", 5000000))
    area_m2 = polygon_area_m2(points)
    if area_m2 <= 0:
        return None, Response(
            {"puntos": ["No se pudo calcular un polígono válido para el proyecto."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if area_m2 > max_area_m2:
        return None, Response(
            {
                "puntos": [
                    "El área del proyecto excede el límite permitido. Ajusta el trazado."
                ]
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    return points, None


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

    data = {
        "nombreproyecto": request.data.get("nombreproyecto"),
        "longitud": request.data.get("longitud"),
        "latitud": request.data.get("latitud"),
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
    }

    serializer = ProyectoSerializer(data=data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        proyecto = serializer.save()

        puntos_bulk = []
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

        nuevas_imagenes = []
        for img in request.FILES.getlist("imagenes"):
            validate_uploaded_image(img)
            img.name = build_secure_image_name(
                inmobiliaria_id=inmobiliaria_usuario.idinmobiliaria,
                proyecto_id=proyecto.idproyecto,
                image_type="proyecto",
                original_name=img.name,
            )
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
    return Response(
        {
            "proyecto": serializer.data,
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
    if (
        not inmobiliaria_usuario
        or proyecto.idinmobiliaria_id != inmobiliaria_usuario.idinmobiliaria
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

    serializer = ProyectoSerializer(proyecto, data=request.data, partial=True)
    if serializer.is_valid():
        with transaction.atomic():
            serializer.save()
            if "puntos" in request.data:
                puntos_data_raw = _parse_json_list(request.data.get("puntos", []))
                puntos_data, puntos_error = _validate_project_points(puntos_data_raw)
                if puntos_error:
                    transaction.set_rollback(True)
                    return puntos_error
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
        log_audit_event(
            request,
            "proyecto_update",
            status_code=status.HTTP_200_OK,
            success=True,
            target_resource="proyecto",
            target_id=idproyecto,
        )
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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

        if proyecto.idinmobiliaria_id != inmobiliaria_usuario.idinmobiliaria:
            return Response(
                {"error": "No tienes permisos para eliminar este proyecto."},
                status=status.HTTP_403_FORBIDDEN,
            )

        with transaction.atomic():
            # 🔹 Eliminar primero relaciones dependientes
            ClickProyectos.objects.filter(idproyecto=idproyecto).delete()
            ClicksContactos.objects.filter(idproyecto=idproyecto).delete()
            Puntos.objects.filter(idlote__idproyecto=idproyecto).delete()
            Imagenes.objects.filter(idlote__idproyecto=idproyecto).delete()
            Lote.objects.filter(idproyecto=idproyecto).delete()
            ImagenesProyecto.objects.filter(idproyecto=idproyecto).delete()
            PuntosProyecto.objects.filter(idproyecto=idproyecto).delete()
            proyecto.delete()

        log_audit_event(
            request,
            "proyecto_delete",
            status_code=status.HTTP_200_OK,
            success=True,
            target_resource="proyecto",
            target_id=idproyecto,
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
