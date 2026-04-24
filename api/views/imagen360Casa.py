from rest_framework.decorators import api_view, permission_classes, throttle_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.db import transaction
import json
from api.models import *
from api.serializers import *
@api_view(['POST'])
@permission_classes([AllowAny])
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
        return Response({"error": "idproyecto es requerido"}, status=400)

    proyecto_instancia = Proyecto.objects.filter(idproyecto=id_proyecto).first()
    if not proyecto_instancia:
        return Response({"error": "Proyecto no encontrado"}, status=404)

    lote_instancia = Lote.objects.filter(idlote=id_lote).first() if id_lote else None

    if len(nombres) != len(archivos):
        return Response({"error": "La cantidad de nombres e imagenes no coinciden"}, status=400)

    if len(draft_ids) != len(archivos):
        return Response({"error": "La cantidad de draft_ids e imagenes no coinciden"}, status=400)

    try:
        conexiones = json.loads(conexiones_raw) if conexiones_raw else []
    except json.JSONDecodeError:
        return Response({"error": "conexiones debe ser un JSON valido"}, status=400)

    if not isinstance(conexiones, list):
        return Response({"error": "conexiones debe ser una lista"}, status=400)

    overlays_2d_payload = None
    if overlays_2d_raw:
        try:
            overlays_2d_payload = json.loads(overlays_2d_raw)
        except json.JSONDecodeError:
            return Response({"error": "overlays_2d debe ser un JSON valido"}, status=400)

    try:
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
                resolved_layouts = []

                for layout in layouts:
                    resolved_image_id = resolver_id_imagen(
                        layout.get('imageId') or layout.get('imagenId') or layout.get('id_imagen')
                    )
                    if resolved_image_id is None:
                        continue
                    layout_copy = dict(layout)
                    layout_copy['imageId'] = resolved_image_id
                    resolved_layouts.append(layout_copy)

                overlays_2d_resolved['layouts'] = resolved_layouts
                overlays_2d_json = json.dumps(overlays_2d_resolved)

                for layout in resolved_layouts:
                    Imagen360.objects.filter(id_imagen=layout['imageId']).update(
                        overlays_2d=overlays_2d_json
                    )

            for conexion in conexiones:
                origen_id = resolver_id_imagen(conexion.get('origenId'))
                destino_id = resolver_id_imagen(conexion.get('destinoId'))
                yaw = conexion.get('yaw')
                pitch = conexion.get('pitch')

                if origen_id is None or destino_id is None:
                    raise ValueError("Hay conexiones con ids de imagen invalidos")

                if yaw is None or pitch is None:
                    raise ValueError("Hay conexiones sin yaw o pitch")

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

    except Exception as e:
        return Response({"error": str(e)}, status=500)


@api_view(['POST'])
@permission_classes([AllowAny])
# @throttle_classes([ClickRateThrottle]) # Asegurate de que ClickRateThrottle este bien definido
@parser_classes([MultiPartParser, FormParser])
def guardar_imagenes_360_multiple(request):
    # 1. Obtener listas de datos
    nombres = request.data.getlist('nombres')  
    archivos = request.FILES.getlist('imagenes') 
    
    id_proyecto = request.data.get('idproyecto')
    id_lote = request.data.get('idlote')

    # Validación de paridad (Debe haber un nombre por cada imagen)
    if not archivos:
        return Response({"error": "No se enviaron imágenes"}, status=400)
    
    if len(nombres) != len(archivos):
        return Response({"error": "La cantidad de nombres e imágenes no coinciden"}, status=400)

    # Buscar instancias una sola vez fuera del bucle para optimizar
    proyecto_instancia = Proyecto.objects.filter(idproyecto=id_proyecto).first() if id_proyecto else None
    lote_instancia = Lote.objects.filter(idlote=id_lote).first() if id_lote else None

    resultados = []
    
    try:
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

    except Exception as e:
        return Response({"error": str(e)}, status=500)
    

@api_view(['GET']) # Permitimos GET para que sea fácil de probar
@permission_classes([AllowAny])
def get_imagenes_360_multiple(request, idproyecto):
    # 1. Obtenemos todas las imágenes filtradas por el ID del proyecto
    imagenes = Imagen360.objects.filter(idproyecto=idproyecto)
    
    # 2. Serializamos la lista (many=True es obligatorio porque son varios objetos)
    serializer = Imagen360Serializer(imagenes, many=True)
    
    # 3. Retornamos los datos correctamente
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([AllowAny])
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

        proyecto = Proyecto.objects.get(idproyecto=id_proyecto)
        lote = Lote.objects.filter(idlote=id_lote).first() if id_lote else None

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

    except Exception as e:
        return Response({"error": str(e)}, status=500)   
    
@api_view(['POST'])
@permission_classes([AllowAny])
def conectar_puntos_360(request):
    try:
        id_origen = request.data.get('id_origen')
        id_destino = request.data.get('id_destino')
        yaw = request.data.get('yaw')
        pitch = request.data.get('pitch')

        Hotspot360.objects.create(
            imagen_origen_id=id_origen,
            imagen_destino_id=id_destino,
            yaw=yaw,
            pitch=pitch,
            texto_ayuda="Ir"
        )

        return Response({"message": "ok"}, status=201)

    except Exception as e:
        return Response({"error": str(e)}, status=500)
    
    
    
@api_view(['GET'])
@permission_classes([AllowAny])
def get_hotspots_por_imagen(request, id_imagen):
    hotspots = Hotspot360.objects.filter(imagen_origen_id=id_imagen)

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

@api_view(['DELETE'])
def eliminar_hotspot(request, id):
    Hotspot360.objects.filter(id_hotspot=id).delete()
    return Response({"ok": True})
