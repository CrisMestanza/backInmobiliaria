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
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from api.authentication import CustomJWTAuthentication
from api.audit import log_audit_event
from api.file_cleanup import delete_files_and_empty_dirs
from api.models import Imagenes, Lote, Proyecto, Puntos, PuntosProyecto
from api.security_uploads import build_unique_image_name, validate_uploaded_image
from api.serializers import (
    ImagenesSerializer,
    LoteMapaSerializer,
    LoteMapaDetalleSerializer,
    ProyectoMapaDetalleSerializer,
    InmobiliariaSerializer,
    LoteSerializer,
    ProyectoSerializer,
)
from api.views.permissions import IsOwnerOfLote, IsSameInmobiliaria
from api.views.permissions import is_project_owned_by_user
from api.validation_utils import parse_polygon_points, polygon_area_m2


def _parse_json_list(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return value if isinstance(value, list) else []


def _parse_int_list(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []
    parsed = []
    for item in value:
        try:
            parsed.append(int(item))
        except (TypeError, ValueError):
            continue
    return parsed


def _ensure_activated_user(request):
    if not getattr(request.user, "is_active", False) or getattr(request.user, "estado", 0) != 1:
        return Response(
            {"error": "Primero debes activar tu cuenta para poder crear lotes o proyectos."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _validate_lote_points(raw_points):
    points = parse_polygon_points(raw_points)
    if len(points) < 3:
        return None, Response(
            {"puntos": ["El lote/inmueble debe tener al menos 3 puntos válidos."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    max_area_m2 = float(getattr(settings, "LOTE_MAX_POLYGON_AREA_M2", 500000))
    area_m2 = polygon_area_m2(points)
    if area_m2 <= 0:
        return None, Response(
            {"puntos": ["No se pudo calcular un polígono válido para el lote."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if area_m2 > max_area_m2:
        return None, Response(
            {"puntos": ["El área del lote excede el límite permitido."]},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return points, None


# Nuevo
@api_view(["GET"])
@permission_classes([AllowAny])
def get_lotes_con_puntos(_request, idproyecto):
    lotes = (
        Lote.objects.filter(idproyecto=idproyecto)
        .only(
            "idlote",
            "nombre",
            "precio",
            "vendido",
            "latitud",
            "longitud",
            "idproyecto_id",
        )
        .prefetch_related(
            Prefetch(
                "puntos_set",
                queryset=Puntos.objects.only(
                    "idlote_id", "latitud", "longitud", "orden"
                ).order_by("orden"),
            )
        )
    )

    serializer = LoteMapaSerializer(lotes, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def mapa_lote_detalle(_request, idlote):
    lote = (
        Lote.objects.filter(idlote=idlote)
        .select_related("idproyecto__idinmobiliaria")
        .prefetch_related(
            Prefetch(
                "puntos_set",
                queryset=Puntos.objects.only(
                    "idlote_id", "latitud", "longitud", "orden"
                ).order_by("orden"),
            )
        )
        .first()
    )
    if not lote:
        return Response({"error": "Lote no encontrado"}, status=status.HTTP_404_NOT_FOUND)

    proyecto = lote.idproyecto
    inmobiliaria = proyecto.idinmobiliaria if proyecto else None

    return Response(
        {
            "lote": LoteMapaDetalleSerializer(lote).data,
            "proyecto": ProyectoMapaDetalleSerializer(proyecto).data if proyecto else None,
            "inmobiliaria": InmobiliariaSerializer(inmobiliaria).data if inmobiliaria else None,
        }
    )


# ---


@api_view(["GET"])
@permission_classes([AllowAny])
def list_lotes(_request):
    lotes = Lote.objects.select_related(
        "idproyecto", "idproyecto__idinmobiliaria", "idtipoinmobiliaria"
    ).all()
    serializer = LoteSerializer(lotes, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def lote(_request, idproyecto):
    lotes = Lote.objects.filter(idproyecto=idproyecto).select_related(
        "idproyecto", "idproyecto__idinmobiliaria", "idtipoinmobiliaria"
    )
    serializer = LoteSerializer(lotes, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def getLote(request, idproyecto):
    if not is_project_owned_by_user(idproyecto, request.user):
        return Response(
            {"error": "No tienes permisos para ver estos lotes."},
            status=status.HTTP_403_FORBIDDEN,
        )

    lote = Lote.objects.filter(idproyecto=idproyecto).select_related(
        "idproyecto", "idproyecto__idinmobiliaria", "idtipoinmobiliaria"
    )
    serializer = LoteSerializer(lote, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def registerLote(request):
    blocked = _ensure_activated_user(request)
    if blocked:
        return blocked

    if request.method == "POST":
        project_id = request.data.get("idproyecto")
        if not project_id or not is_project_owned_by_user(project_id, request.user):
            return Response(
                {"error": "No tienes permisos para crear lotes en este proyecto."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if not PuntosProyecto.objects.filter(idproyecto=project_id).exists():
            return Response(
                {"error": "El proyecto debe tener puntos definidos antes de crear lotes."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        idtipoinmobiliaria = request.data.get("idtipoinmobiliaria")
        if not idtipoinmobiliaria:
            return Response(
                {"idtipoinmobiliaria": ["El tipo de inmobiliaria es obligatorio."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        puntos_data_raw = _parse_json_list(request.data.get("puntos", []))
        puntos_data, puntos_error = _validate_lote_points(puntos_data_raw)
        if puntos_error:
            return puntos_error

        data = {
            "idtipoinmobiliaria": idtipoinmobiliaria,
            "idproyecto": request.data.get("idproyecto"),
            "nombre": request.data.get("nombre"),
            "latitud": request.data.get("latitud"),
            "longitud": request.data.get("longitud"),
            "estado": 1,
            "descripcion": request.data.get("descripcion"),
            "precio": request.data.get("precio"),
            "vendido": request.data.get("vendido"),
            # medidas
            "area_total_m2": request.data.get("area_total_m2") or "0",
            "ancho": request.data.get("ancho"),
            "largo": request.data.get("largo"),
            # cantidades
            "dormitorios": request.data.get("dormitorios"),
            "banos": request.data.get("banos"),
            "cuartos": request.data.get("cuartos"),
            # booleanos (0 / 1)
            "titulo_propiedad": request.data.get("titulo_propiedad"),
            "cochera": request.data.get("cochera"),
            "cocina": request.data.get("cocina"),
            "sala": request.data.get("sala"),
            "patio": request.data.get("patio"),
            "jardin": request.data.get("jardin"),
            "terraza": request.data.get("terraza"),
            "azotea": request.data.get("azotea"),
        }

        serializer = LoteSerializer(data=data)
        if serializer.is_valid():
            lote = serializer.save()
            last_id = lote.idlote

            puntos_bulk = []
            for idx, punto in enumerate(puntos_data):
                lat = punto.get("latitud", punto.get("lat"))
                lng = punto.get("longitud", punto.get("lng"))
                if lat is None or lng is None:
                    continue
                puntos_bulk.append(
                    Puntos(
                        idlote=lote,
                        latitud=lat,
                        longitud=lng,
                        estado=1,
                        orden=idx + 1,
                    )
                )
            if puntos_bulk:
                Puntos.objects.bulk_create(puntos_bulk, batch_size=500)

            nuevas_imagenes = []

            imagenes_files = request.FILES.getlist("imagenes")
            for archivo in imagenes_files:
                validate_uploaded_image(archivo)
                archivo.name = build_unique_image_name(archivo.name)
                imagen_serializer = ImagenesSerializer(
                    data={"idlote": last_id, "imagen": archivo}
                )
                if imagen_serializer.is_valid():
                    imagen_serializer.save()
                    nuevas_imagenes.append(imagen_serializer.data)

            imagenes_json = _parse_json_list(request.data.get("imagenes_creadas", []))
            for img in imagenes_json:
                img["idlote"] = last_id
                imagen_serializer = ImagenesSerializer(data=img)
                if imagen_serializer.is_valid():
                    imagen_serializer.save()
                    nuevas_imagenes.append(imagen_serializer.data)

            log_audit_event(
                request,
                "lote_create",
                status_code=status.HTTP_201_CREATED,
                success=True,
                target_resource="lote",
                target_id=lote.idlote,
                detail={"puntos": len(puntos_bulk), "imagenes": len(nuevas_imagenes)},
            )
            return Response(
                {
                    "lote": serializer.data,
                    "imagenes_creadas": nuevas_imagenes,
                    "puntos_creados": len(puntos_bulk),
                },
                status=201,
            )

        return Response(serializer.errors, status=400)


@api_view(["PUT"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def updateLote(request, idlote):
    try:
        lote = (
            Lote.objects.select_related("idproyecto__idinmobiliaria__idusuario")
            .filter(idlote=idlote)
            .first()
        )
        if not lote:
            return Response(
                {"error": "Lote no encontrado"}, status=status.HTTP_404_NOT_FOUND
            )

        # Verificar permisos
        if not (
            IsOwnerOfLote().has_object_permission(request, None, lote)
            or IsSameInmobiliaria().has_object_permission(request, None, lote)
        ):
            return Response(
                {"error": "No tienes permisos para editar este lote."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Actualizar datos principales
        serializer = LoteSerializer(lote, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            image_paths_to_delete = []
            lote = serializer.save()

            # Actualizar puntos
            puntos_raw = _parse_json_list(request.data.get("puntos", []))
            if "puntos" in request.data:
                puntos_valid, puntos_error = _validate_lote_points(puntos_raw)
                if puntos_error:
                    transaction.set_rollback(True)
                    return puntos_error
                lote.puntos_set.all().delete()
                puntos_bulk = []
                for idx, p in enumerate(puntos_valid):
                    puntos_bulk.append(
                        Puntos(
                            idlote=lote,
                            latitud=p["latitud"],
                            longitud=p["longitud"],
                            estado=1,
                            orden=idx + 1,
                        )
                    )
                if puntos_bulk:
                    Puntos.objects.bulk_create(puntos_bulk, batch_size=500)
            else:
                puntos_bulk = []

            # Actualizar imágenes
            nuevas_imagenes = []
            for archivo in request.FILES.getlist("imagenes"):
                validate_uploaded_image(archivo)
                archivo.name = build_unique_image_name(archivo.name)
                img = ImagenesSerializer(
                    data={"idlote": lote.idlote, "imagen": archivo}
                )
                if img.is_valid():
                    img.save()
                    nuevas_imagenes.append(img.data)

            for img_json in _parse_json_list(request.data.get("imagenes_creadas", [])):
                img_json["idlote"] = lote.idlote
                img = ImagenesSerializer(data=img_json)
                if img.is_valid():
                    img.save()
                    nuevas_imagenes.append(img.data)

            if "imagenes_eliminadas" in request.data:
                ids_to_delete = _parse_int_list(request.data.get("imagenes_eliminadas", []))
                if ids_to_delete:
                    imagenes_qs = Imagenes.objects.filter(
                        idlote=lote.idlote,
                        idimagenes__in=ids_to_delete,
                    )
                    image_paths_to_delete.extend(
                        str(path)
                        for path in imagenes_qs.values_list("imagen", flat=True)
                        if path
                    )
                    imagenes_qs.delete()

            if image_paths_to_delete:
                transaction.on_commit(
                    lambda paths=image_paths_to_delete: delete_files_and_empty_dirs(paths)
                )

        log_audit_event(
            request,
            "lote_update",
            status_code=status.HTTP_200_OK,
            success=True,
            target_resource="lote",
            target_id=idlote,
            detail={"puntos": len(puntos_bulk), "imagenes": len(nuevas_imagenes)},
        )
        return Response(
            {
                "message": "Lote actualizado correctamente",
                "lote": serializer.data,
                "puntos": len(puntos_bulk),
                "imagenes": nuevas_imagenes,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"error": f"Ocurrió un error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["PATCH"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def updateLoteVendido(request, idlote):
    try:
        lote = (
            Lote.objects.select_related("idproyecto__idinmobiliaria__idusuario")
            .filter(idlote=idlote)
            .first()
        )
        if not lote:
            return Response(
                {"error": "Lote no encontrado"}, status=status.HTTP_404_NOT_FOUND
            )

        if not (
            IsOwnerOfLote().has_object_permission(request, None, lote)
            or IsSameInmobiliaria().has_object_permission(request, None, lote)
        ):
            return Response(
                {"error": "No tienes permisos para editar este lote."},
                status=status.HTTP_403_FORBIDDEN,
            )

        vendido = request.data.get("vendido")
        if vendido is None:
            return Response(
                {"error": 'El campo "vendido" es requerido'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        lote.vendido = vendido
        lote.save(update_fields=["vendido"])

        log_audit_event(
            request,
            "lote_update_vendido",
            status_code=status.HTTP_200_OK,
            success=True,
            target_resource="lote",
            target_id=idlote,
            detail={"vendido": vendido},
        )
        return Response(
            {
                "message": "Estado de venta actualizado",
                "idlote": lote.idlote,
                "vendido": lote.vendido,
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"error": f"Ocurrió un error: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def rangoPrecio(_request, rango):
    try:
        num1, num2 = rango.split("-")

        num1 = float(num1.replace(",", ""))
        num2 = float(num2.replace(",", ""))

        lote = Lote.objects.filter(precio__range=(num1, num2))
        proyecto = Proyecto.objects.filter(
            precio__range=(num1, num2), idtipoinmobiliaria=2
        )

        serializer_lote = LoteSerializer(lote, many=True)
        serializer_proyecto = ProyectoSerializer(proyecto, many=True)

        return Response(
            {"lotes": serializer_lote.data, "proyectos": serializer_proyecto.data}
        )

    except Exception as e:
        return Response({"error": str(e)}, status=400)


@api_view(["DELETE"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def deleteLote(request, idlote):
    try:
        lote = (
            Lote.objects.select_related("idproyecto__idinmobiliaria__idusuario")
            .filter(idlote=idlote)
            .first()
        )

        if not lote:
            return Response(
                {"error": "El lote no existe."}, status=status.HTTP_404_NOT_FOUND
            )

        is_owner = IsOwnerOfLote().has_object_permission(request, None, lote)
        is_same_inm = IsSameInmobiliaria().has_object_permission(request, None, lote)

        if not (is_owner or is_same_inm):
            return Response(
                {"error": "No tienes permisos para eliminar este lote."},
                status=status.HTTP_403_FORBIDDEN,
            )

        with transaction.atomic():
            file_paths = [
                str(path)
                for path in Imagenes.objects.filter(idlote=idlote).values_list(
                    "imagen", flat=True
                )
                if path
            ]
            puntos_borrados = Puntos.objects.filter(idlote=idlote).delete()
            imagenes_borradas = Imagenes.objects.filter(idlote=idlote).delete()
            lote.delete()
            transaction.on_commit(lambda: delete_files_and_empty_dirs(file_paths))

        log_audit_event(
            request,
            "lote_delete",
            status_code=status.HTTP_200_OK,
            success=True,
            target_resource="lote",
            target_id=idlote,
            detail={
                "puntos_eliminados": puntos_borrados[0],
                "imagenes_eliminadas": imagenes_borradas[0],
            },
        )
        return Response(
            {
                "message": f"Lote {idlote} y sus relaciones fueron eliminados correctamente.",
                "detalles": {
                    "puntos_eliminados": puntos_borrados[0],
                    "imagenes_eliminadas": imagenes_borradas[0],
                },
            },
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"error": f"Ocurrió un error al eliminar el lote: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def registerLotesMasivo(request):
    blocked = _ensure_activated_user(request)
    if blocked:
        return blocked

    try:
        # Extraer lotes del FormData
        lotes = []
        for key, value in request.data.items():
            if key.startswith("lotes["):
                try:
                    lotes.append(json.loads(value))
                except json.JSONDecodeError:
                    return Response(
                        {"error": f"JSON inválido en {key}"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        if not isinstance(lotes, list) or len(lotes) == 0:
            return Response({"error": "Se esperaba una lista de lotes"}, status=400)

        lotes_creados = []
        errores = []

        with transaction.atomic():
            for idx, lote_data in enumerate(lotes):
                try:
                    # Extraer puntos y eliminar de lote_data
                    puntos_data = lote_data.pop("puntos", [])

                    # Determinar latitud y longitud para el lote (primer punto si existe)
                    if puntos_data:
                        primer_punto = puntos_data[0]
                        lat = (
                            primer_punto.get("lat") or primer_punto.get("latitud") or 0
                        )
                        lng = (
                            primer_punto.get("lng") or primer_punto.get("longitud") or 0
                        )
                    else:
                        lat, lng = 0, 0

                    # Preparar datos para Lote
                    data_lote = {
                        "idtipoinmobiliaria": lote_data.get("idtipoinmobiliaria"),
                        "idproyecto": lote_data.get("idproyecto"),
                        "nombre": lote_data.get("nombre"),
                        "latitud": lat,
                        "longitud": lng,
                        "estado": 1,
                        "descripcion": lote_data.get("descripcion", ""),
                        "precio": lote_data.get("precio", 0),
                        "vendido": lote_data.get("vendido", 0),
                        # medidas
                        "area_total_m2": lote_data.get("area_total_m2", "0"),
                        "ancho": lote_data.get("ancho"),
                        "largo": lote_data.get("largo"),
                        # cantidades
                        "dormitorios": lote_data.get("dormitorios"),
                        "banos": lote_data.get("banos"),
                        "cuartos": lote_data.get("cuartos"),
                        # booleanos
                        "titulo_propiedad": lote_data.get("titulo_propiedad"),
                        "cochera": lote_data.get("cochera"),
                        "cocina": lote_data.get("cocina"),
                        "sala": lote_data.get("sala"),
                        "patio": lote_data.get("patio"),
                        "jardin": lote_data.get("jardin"),
                        "terraza": lote_data.get("terraza"),
                        "azotea": lote_data.get("azotea"),
                    }

                    serializer = LoteSerializer(data=data_lote)
                    if serializer.is_valid():
                        project_id = data_lote.get("idproyecto")
                        if not project_id or not is_project_owned_by_user(
                            project_id, request.user
                        ):
                            errores.append(
                                {
                                    "indice": idx,
                                    "nombre": lote_data.get("nombre", f"Lote {idx}"),
                                    "error": "Sin permisos sobre el proyecto",
                                }
                            )
                            continue
                        if not data_lote.get("idtipoinmobiliaria"):
                            errores.append(
                                {
                                    "indice": idx,
                                    "nombre": lote_data.get("nombre", f"Lote {idx}"),
                                    "error": "idtipoinmobiliaria es obligatorio",
                                }
                            )
                            continue
                        if not PuntosProyecto.objects.filter(idproyecto=project_id).exists():
                            errores.append(
                                {
                                    "indice": idx,
                                    "nombre": lote_data.get("nombre", f"Lote {idx}"),
                                    "error": "Proyecto sin puntos definidos",
                                }
                            )
                            continue
                        puntos_valid, puntos_error = _validate_lote_points(puntos_data)
                        if puntos_error:
                            errores.append(
                                {
                                    "indice": idx,
                                    "nombre": lote_data.get("nombre", f"Lote {idx}"),
                                    "error": "Puntos inválidos o insuficientes",
                                }
                            )
                            continue

                        lote = serializer.save()

                        # Guardar puntos
                        puntos_bulk = []
                        for punto in puntos_valid:
                            puntos_bulk.append(
                                Puntos(
                                    idlote=lote,
                                    latitud=punto["latitud"],
                                    longitud=punto["longitud"],
                                    estado=1,
                                )
                            )
                        if puntos_bulk:
                            Puntos.objects.bulk_create(puntos_bulk, batch_size=500)

                        # Guardar imágenes
                        imagenes = request.FILES.getlist(f"imagenes_{idx}")
                        imagenes_creadas = []
                        for img in imagenes:
                            validate_uploaded_image(img)
                            img.name = build_unique_image_name(img.name)
                            img_serializer = ImagenesSerializer(
                                data={"idlote": lote.idlote, "imagen": img}
                            )
                            if img_serializer.is_valid():
                                img_serializer.save()
                                imagenes_creadas.append(img_serializer.data)

                        lotes_creados.append(
                            {
                                "lote": serializer.data,
                                "puntos": len(puntos_bulk),
                                "imagenes": imagenes_creadas,
                            }
                        )
                    else:
                        errores.append(
                            {
                                "indice": idx,
                                "nombre": lote_data.get("nombre", f"Lote {idx}"),
                                "errores": serializer.errors,
                            }
                        )

                except Exception as e:
                    errores.append(
                        {
                            "indice": idx,
                            "nombre": lote_data.get("nombre", f"Lote {idx}"),
                            "error": str(e),
                        }
                    )

        response_data = {
            "total_recibidos": len(lotes),
            "total_creados": len(lotes_creados),
            "total_errores": len(errores),
            "lotes_creados": lotes_creados,
        }
        if errores:
            response_data["errores"] = errores

        status_code = (
            status.HTTP_201_CREATED
            if len(lotes_creados) > 0
            else status.HTTP_400_BAD_REQUEST
        )
        log_audit_event(
            request,
            "lote_register_masivo",
            status_code=status_code,
            success=len(lotes_creados) > 0,
            target_resource="lote",
            detail={
                "total_recibidos": len(lotes),
                "total_creados": len(lotes_creados),
                "total_errores": len(errores),
            },
        )
        return Response(response_data, status=status_code)

    except Exception as e:
        return Response({"error": str(e)}, status=400)
