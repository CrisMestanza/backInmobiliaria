from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.http import HttpResponseRedirect
import io
import json
import logging
import os
import traceback
from rest_framework.exceptions import ValidationError
from api.models import *
from api.serializers import *
from api.authentication import CustomJWTAuthentication
from api.security_uploads import build_unique_image_name, validate_uploaded_image
from api.throttling import PublicMapRateThrottle, Upload360RateThrottle
from api.upload_limits import enforce_file_batch_limits
from api.views.permissions import is_project_owned_by_user

logger = logging.getLogger(__name__)


def _plain_error_text(detail):
    if isinstance(detail, dict):
        messages = []
        for value in detail.values():
            messages.append(_plain_error_text(value))
        return " ".join(message for message in messages if message)
    if isinstance(detail, (list, tuple)):
        return " ".join(_plain_error_text(item) for item in detail if item)
    return str(detail).strip()


def _client_error(message, status_code=400, code="tour_360_validation_error", extra=None):
    payload = {"error": message, "code": code}
    if extra:
        payload.update(extra)
    return Response(payload, status=status_code)


def _validation_error_response(exc, *, file_name=None):
    message = _plain_error_text(getattr(exc, "detail", exc)) or "Datos invalidos para el tour 360."
    if file_name:
        message = f"Imagen '{file_name}': {message}"
    status_code = 413 if "tamaño máximo" in message.lower() or "excede" in message.lower() else 400
    return _client_error(message, status_code=status_code, code="tour_360_validation_error")


def _generic_error(status_code=500, exc=None):
    if exc is not None:
        logger.error("Error en imagen360Casa: %s\n%s", exc, traceback.format_exc())
    return Response(
        {
            "error": "No se pudo procesar la solicitud del tour 360. Intenta nuevamente.",
            "code": "tour_360_server_error",
        },
        status=status_code,
    )


def _ensure_project_owner(request, project_id):
    if not project_id or not is_project_owned_by_user(project_id, request.user):
        return Response(
            {"error": "No tienes permisos para modificar este tour 360."},
            status=403,
        )
    return None


def _validate_360_files(files):
    files = enforce_file_batch_limits(
        files,
        max_files_setting="MAX_360_UPLOAD_FILES",
        max_total_mb_setting="MAX_360_UPLOAD_TOTAL_MB",
        default_max_files=20,
        default_total_mb=80,
    )
    for uploaded in files:
        try:
            validate_uploaded_image(uploaded)
        except ValidationError as exc:
            raise ValidationError(
                f"Imagen '{getattr(uploaded, 'name', 'archivo')}': {_plain_error_text(exc.detail)}"
            ) from exc
        uploaded.name = build_unique_image_name(uploaded.name)
    return files


@api_view(['POST'])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([Upload360RateThrottle])
@parser_classes([MultiPartParser, FormParser])
def guardar_tour_360_completo(request):
    """
    Guarda un tour 360 completo enviado desde el frontend como borrador local.

    Espera multipart/form-data con:
    - idproyecto: id del proyecto
    - idlote: opcional
    - imagenes: lista de archivos
    - nombres: lista de nombres, en el mismo orden que imagenes
    - draft_ids: lista de ids temporales del frontend, en el mismo orden que imagenes
    - conexiones: JSON string con items { origenId, destinoId, yaw, pitch, destinoNombre }

    El frontend puede mandar conexiones usando ids temporales tipo "draft-...".
    Esta vista crea las imagenes, mapea esos ids temporales a ids reales y luego crea los hotspots.
    """
    id_proyecto = request.data.get('idproyecto')
    id_lote = request.data.get('idlote')
    archivos = request.FILES.getlist('imagenes')
    nombres = request.data.getlist('nombres')
    draft_ids = request.data.getlist('draft_ids')
    conexiones_raw = request.data.get('conexiones', '[]')
    overlays_2d_raw = request.data.get('overlays_2d')

    if not id_proyecto:
        return _client_error("Selecciona un proyecto antes de guardar el tour 360.")
    permission_error = _ensure_project_owner(request, id_proyecto)
    if permission_error:
        return permission_error

    proyecto_instancia = Proyecto.objects.filter(idproyecto=id_proyecto).first()
    if not proyecto_instancia:
        return Response({"error": "Proyecto no encontrado"}, status=404)

    lote_instancia = Lote.objects.filter(idlote=id_lote).first() if id_lote else None
    if lote_instancia and lote_instancia.idproyecto_id != proyecto_instancia.idproyecto:
        return Response({"error": "El lote no pertenece al proyecto."}, status=400)

    if len(nombres) != len(archivos):
        return _client_error("La cantidad de nombres e imagenes no coinciden.")

    if len(draft_ids) != len(archivos):
        return _client_error("La cantidad de draft_ids e imagenes no coinciden.")

    try:
        conexiones = json.loads(conexiones_raw) if conexiones_raw else []
    except json.JSONDecodeError:
        return _client_error("Las conexiones del tour 360 tienen un formato invalido.")

    if not isinstance(conexiones, list):
        return _client_error("Las conexiones del tour 360 deben enviarse como una lista.")
    if len(conexiones) > int(getattr(settings, "MAX_360_CONNECTIONS_PER_REQUEST", 200)):
        return _client_error("Demasiadas conexiones 360 en una solicitud.")

    overlays_2d_payload = None
    if overlays_2d_raw:
        try:
            overlays_2d_payload = json.loads(overlays_2d_raw)
        except json.JSONDecodeError:
            return _client_error("El overlay 2D del tour 360 tiene un formato invalido.")

    try:
        archivos = _validate_360_files(archivos)
        with transaction.atomic():
            draft_to_real_id = {}
            imagenes_creadas = []
            hotspots_creados = []

            def resolver_id_imagen(valor):
                valor = str(valor)
                if valor in draft_to_real_id:
                    return draft_to_real_id[valor]
                try:
                    return int(valor)
                except (TypeError, ValueError):
                    return None

            for index, archivo in enumerate(archivos):
                nueva_imagen = Imagen360.objects.create(
                    nombre=nombres[index],
                    idproyecto=proyecto_instancia,
                    idlote=lote_instancia,
                    imagen=archivo,
                    yaw=0,
                    pitch=0,
                    overlays_2d=None
                )
                draft_to_real_id[str(draft_ids[index])] = nueva_imagen.id_imagen
                imagenes_creadas.append({
                    "draft_id": str(draft_ids[index]),
                    "id_imagen": nueva_imagen.id_imagen,
                    "nombre": nueva_imagen.nombre,
                    "imagen": nueva_imagen.imagen.url if nueva_imagen.imagen else None,
                })

            overlays_2d_resolved = None
            if isinstance(overlays_2d_payload, dict):
                overlays_2d_resolved = dict(overlays_2d_payload)
                layouts = overlays_2d_payload.get('layouts') or []
                anchored_overlays = overlays_2d_payload.get('anchoredOverlays') or overlays_2d_payload.get('panoramaOverlays') or []
                resolved_layouts = []
                resolved_anchored_overlays = []
                overlay_image_ids = set()

                for layout in layouts:
                    resolved_image_id = resolver_id_imagen(
                        layout.get('imageId') or layout.get('imagenId') or layout.get('id_imagen')
                    )
                    if resolved_image_id is None:
                        continue
                    layout_copy = dict(layout)
                    layout_copy['imageId'] = resolved_image_id
                    resolved_layouts.append(layout_copy)
                    overlay_image_ids.add(resolved_image_id)

                if isinstance(anchored_overlays, list):
                    for overlay in anchored_overlays:
                        if not isinstance(overlay, dict):
                            continue
                        resolved_image_id = resolver_id_imagen(
                            overlay.get('imageId') or overlay.get('imagenId') or overlay.get('id_imagen')
                        )
                        if resolved_image_id is None:
                            continue
                        overlay_copy = dict(overlay)
                        overlay_copy['imageId'] = resolved_image_id
                        resolved_anchored_overlays.append(overlay_copy)
                        overlay_image_ids.add(resolved_image_id)

                overlays_2d_resolved['layouts'] = resolved_layouts
                overlays_2d_resolved['anchoredOverlays'] = resolved_anchored_overlays
                overlays_2d_json = json.dumps(overlays_2d_resolved, separators=(',', ':'))

                for image_id in overlay_image_ids:
                    Imagen360.objects.filter(id_imagen=image_id, idproyecto=proyecto_instancia).update(
                        overlays_2d=overlays_2d_json
                    )

            for conexion in conexiones:
                origen_id = resolver_id_imagen(conexion.get('origenId'))
                destino_id = resolver_id_imagen(conexion.get('destinoId'))
                yaw = conexion.get('yaw')
                pitch = conexion.get('pitch')

                if origen_id is None or destino_id is None:
                    return _client_error("Hay conexiones 360 con imagenes invalidas o no guardadas.")

                if yaw is None or pitch is None:
                    return _client_error("Hay conexiones 360 incompletas: falta yaw o pitch.")

                hotspot = Hotspot360.objects.create(
                    imagen_origen_id=origen_id,
                    imagen_destino_id=destino_id,
                    yaw=yaw,
                    pitch=pitch,
                    texto_ayuda=f"Ir a {conexion.get('destinoNombre', 'vista 360')}"
                )
                hotspots_creados.append({
                    "id_hotspot": hotspot.id_hotspot,
                    "origen_id": origen_id,
                    "destino_id": destino_id,
                    "yaw": hotspot.yaw,
                    "pitch": hotspot.pitch,
                })

            if overlays_2d_resolved:
                for item in imagenes_creadas:
                    item['overlays_2d'] = overlays_2d_resolved

        return Response({
            "message": "Tour 360 guardado correctamente",
            "imagenes": imagenes_creadas,
            "hotspots": hotspots_creados,
            "image_map": draft_to_real_id,
            "overlays_2d": overlays_2d_resolved,
        }, status=201)

    except ValidationError as e:
        return _validation_error_response(e)
    except ValueError as e:
        return _client_error(str(e) or "Datos invalidos para el tour 360.")
    except Exception as e:
        return _generic_error(exc=e)


@api_view(['POST'])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([Upload360RateThrottle])
@parser_classes([MultiPartParser, FormParser])
def guardar_imagenes_360_multiple(request):
    # 1. Obtener listas de datos
    nombres = request.data.getlist('nombres')  
    archivos = request.FILES.getlist('imagenes') 
    
    id_proyecto = request.data.get('idproyecto')
    id_lote = request.data.get('idlote')
    permission_error = _ensure_project_owner(request, id_proyecto)
    if permission_error:
        return permission_error

    # Validación de paridad (Debe haber un nombre por cada imagen)
    if not archivos:
        return Response({"error": "No se enviaron imágenes"}, status=400)
    
    if len(nombres) != len(archivos):
        return Response({"error": "La cantidad de nombres e imágenes no coinciden"}, status=400)

    # Buscar instancias una sola vez fuera del bucle para optimizar
    proyecto_instancia = Proyecto.objects.filter(idproyecto=id_proyecto).first() if id_proyecto else None
    lote_instancia = Lote.objects.filter(idlote=id_lote).first() if id_lote else None
    if lote_instancia and proyecto_instancia and lote_instancia.idproyecto_id != proyecto_instancia.idproyecto:
        return Response({"error": "El lote no pertenece al proyecto."}, status=400)

    resultados = []
    
    try:
        archivos = _validate_360_files(archivos)
        # 2. Iterar y crear registros
        for i in range(len(archivos)):
            nueva_imagen = Imagen360.objects.create(
                nombre=nombres[i],
                idproyecto=proyecto_instancia,
                idlote=lote_instancia,
                imagen=archivos[i]
            )
            resultados.append({
                "id": nueva_imagen.id_imagen,
                "nombre": nueva_imagen.nombre,
                "url": nueva_imagen.imagen.url
            })

        return Response({
            "message": f"Se guardaron {len(resultados)} imágenes con éxito",
            "imagenes": resultados
        }, status=201)

    except ValidationError as e:
        return _validation_error_response(e)
    except Exception as e:
        return _generic_error(exc=e)


def _generate_thumb_360(original_name, thumb_name):
    """Genera y guarda el thumbnail en un hilo aparte para no bloquear el request."""
    try:
        from PIL import Image
        with default_storage.open(original_name, 'rb') as f:
            img = Image.open(f)
            img.load()
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.thumbnail((2048, 1024), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=75, optimize=True)
        buf.seek(0)
        default_storage.save(thumb_name, ContentFile(buf.read()))
    except Exception as exc:
        logger.error("Error generando thumbnail 360 %s: %s", thumb_name, exc)


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([PublicMapRateThrottle])
def get_thumbnail_imagen360(request, id_imagen):
    """Sirve un thumbnail comprimido (2048x1024, JPEG 75%) de la imagen 360.
    Primera petición: genera en background y redirige a la imagen original.
    Siguientes peticiones: redirige directo al thumbnail (instantáneo)."""
    try:
        obj = Imagen360.objects.get(id_imagen=id_imagen)
    except Imagen360.DoesNotExist:
        return Response({"error": "Imagen no encontrada."}, status=404)

    if not obj.imagen:
        return Response({"error": "Imagen sin archivo."}, status=404)

    original_name = obj.imagen.name
    root, _ext = os.path.splitext(original_name)
    thumb_name = f"{root}_thumb.jpg"

    if default_storage.exists(thumb_name):
        return HttpResponseRedirect(default_storage.url(thumb_name))

    import threading
    t = threading.Thread(target=_generate_thumb_360, args=(original_name, thumb_name), daemon=True)
    t.start()
    return HttpResponseRedirect(obj.imagen.url)


@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([PublicMapRateThrottle])
def get_imagenes_360_multiple(request, idproyecto):
    # 1. Obtenemos todas las imágenes filtradas por el ID del proyecto
    imagenes = (
        Imagen360.objects
        .filter(idproyecto=idproyecto)
        .select_related("idproyecto", "idlote")
        .order_by("id_imagen")
    )
    
    # 2. Serializamos la lista (many=True es obligatorio porque son varios objetos)
    serializer = Imagen360Serializer(imagenes, many=True)
    
    # 3. Retornamos los datos correctamente
    return Response(serializer.data)


@api_view(['POST'])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([Upload360RateThrottle])
@parser_classes([MultiPartParser, FormParser])
def agregar_punto_recorrido(request):
    try:
        id_origen = request.data.get('id_origen')
        yaw = request.data.get('yaw')
        pitch = request.data.get('pitch')
        nombre_destino = request.data.get('nombre_destino')

        id_proyecto = request.data.get('idproyecto')
        id_lote = request.data.get('idlote')
        archivo = request.FILES.get('imagen')
        permission_error = _ensure_project_owner(request, id_proyecto)
        if permission_error:
            return permission_error
        if not id_origen:
            return _client_error("Selecciona una imagen de origen para crear el punto 360.")
        if not nombre_destino:
            return _client_error("Indica un nombre para la nueva vista 360.")
        if yaw is None or pitch is None:
            return _client_error("Selecciona un punto valido dentro de la imagen 360.")
        if not archivo:
            return _client_error("Selecciona una imagen para el nuevo punto 360.")

        proyecto = Proyecto.objects.get(idproyecto=id_proyecto)
        lote = Lote.objects.filter(idlote=id_lote).first() if id_lote else None
        if lote and lote.idproyecto_id != proyecto.idproyecto:
            return Response({"error": "El lote no pertenece al proyecto."}, status=400)
        if archivo:
            _validate_360_files([archivo])

        # 1. Crear nueva imagen
        nueva_img = Imagen360.objects.create(
            nombre=nombre_destino,
            imagen=archivo,
            idproyecto=proyecto,
            idlote=lote
        )

        # 2. Crear hotspot
        Hotspot360.objects.create(
            imagen_origen_id=id_origen,
            imagen_destino=nueva_img,
            yaw=yaw,
            pitch=pitch,
            texto_ayuda=f"Ir a {nombre_destino}"
        )

        return Response({
            "message": "ok",
            "id_imagen": nueva_img.id_imagen,
            "url": nueva_img.imagen.url,
            "nombre": nueva_img.nombre
        }, status=201)

    except ValidationError as e:
        return _validation_error_response(e)
    except ObjectDoesNotExist:
        return _client_error("El proyecto o imagen 360 solicitado no existe.", status_code=404, code="tour_360_not_found")
    except Exception as e:
        return _generic_error(exc=e)

@api_view(['POST'])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([Upload360RateThrottle])
def conectar_puntos_360(request):
    try:
        id_origen = request.data.get('id_origen')
        id_destino = request.data.get('id_destino')
        yaw = request.data.get('yaw')
        pitch = request.data.get('pitch')
        if not id_origen or not id_destino:
            return _client_error("Selecciona una imagen de origen y destino para conectar el tour 360.")
        if yaw is None or pitch is None:
            return _client_error("Selecciona un punto valido dentro de la imagen 360.")
        origin = Imagen360.objects.select_related("idproyecto").filter(id_imagen=id_origen).first()
        destination = Imagen360.objects.select_related("idproyecto").filter(id_imagen=id_destino).first()
        if not origin or not destination or origin.idproyecto_id != destination.idproyecto_id:
            return Response({"error": "Imagenes 360 invalidas."}, status=400)
        permission_error = _ensure_project_owner(request, origin.idproyecto_id)
        if permission_error:
            return permission_error

        Hotspot360.objects.create(
            imagen_origen_id=id_origen,
            imagen_destino_id=id_destino,
            yaw=yaw,
            pitch=pitch,
            texto_ayuda="Ir"
        )

        return Response({"message": "ok"}, status=201)

    except Exception as e:
        return _generic_error(exc=e)

    
    
@api_view(['GET'])
@permission_classes([AllowAny])
@throttle_classes([PublicMapRateThrottle])
def get_hotspots_por_imagen(request, id_imagen):
    try:
        hotspots = (
            Hotspot360.objects
            .filter(imagen_origen_id=id_imagen)
            .select_related("imagen_destino")
            .order_by("id_hotspot")
        )

        data = [
            {
                "id": h.id_hotspot,
                "yaw": h.yaw,
                "pitch": h.pitch,
                "destino": {
                    "id_imagen": h.imagen_destino.id_imagen,
                    "imagen": h.imagen_destino.imagen.url,
                    "nombre": h.imagen_destino.nombre
                }
            }
            for h in hotspots
        ]

        return Response(data)
    except Exception as e:
        return _generic_error(exc=e)

@api_view(['DELETE'])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
@throttle_classes([Upload360RateThrottle])
def eliminar_hotspot(request, id):
    hotspot = Hotspot360.objects.select_related("imagen_origen__idproyecto").filter(id_hotspot=id).first()
    if not hotspot:
        return Response({"ok": True})
    permission_error = _ensure_project_owner(request, hotspot.imagen_origen.idproyecto_id)
    if permission_error:
        return permission_error
    hotspot.delete()
    return Response({"ok": True})
