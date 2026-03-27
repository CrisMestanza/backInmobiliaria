from rest_framework.decorators import api_view, permission_classes, throttle_classes, parser_classes
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from api.models import Imagen360, Proyecto, Lote

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