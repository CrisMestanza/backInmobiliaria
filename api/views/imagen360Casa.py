from rest_framework.decorators import api_view, permission_classes, throttle_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from api.models import *
from api.serializers import *


@api_view(['POST'])
@permission_classes([AllowAny])
# @throttle_classes([ClickRateThrottle]) # Asegúrate de que ClickRateThrottle esté bien definido
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
        # Datos del punto
        id_origen = request.data.get('id_origen')
        yaw = request.data.get('yaw')
        pitch = request.data.get('pitch')
        nombre_destino = request.data.get('nombre_destino')
        
        # Datos de relación GeoHabita
        id_proyecto = request.data.get('idproyecto')
        id_lote = request.data.get('idlote')
        archivo = request.FILES.get('imagen')

        # 1. Creamos la nueva imagen 360 (el destino)
        proyecto = Proyecto.objects.get(idproyecto=id_proyecto)
        lote = Lote.objects.filter(idlote=id_lote).first() if id_lote else None

        nueva_img = Imagen360.objects.create(
            nombre=nombre_destino,
            imagen=archivo,
            idproyecto=proyecto,
            idlote=lote
        )

        # 2. Creamos el Hotspot (la flecha que las une)
        Hotspot360.objects.create(
            imagen_origen_id=id_origen,
            imagen_destino=nueva_img,
            yaw=yaw,
            pitch=pitch,
            texto_ayuda=f"Ir a {nombre_destino}"
        )

        return Response({"message": "Punto de recorrido creado con éxito"}, status=201)
    except Exception as e:
        return Response({"error": str(e)}, status=500)