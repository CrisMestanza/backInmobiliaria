from rest_framework.decorators import api_view
from rest_framework.response import Response
from ..serializers import InmobilariaSerializer, ImagenesSerializer, PuntosSerializer, LoteSerializer
from ..models import Inmobilaria, Imagenes, Puntos, Lote
from rest_framework import status
import json 

@api_view(['GET'])
def list_lotes(request):
    if request.method == 'GET':
        lotes = Lote.objects.all()
        serializer = LoteSerializer(lotes, many=True)
        return Response(serializer.data)

@api_view(['GET'])
def lote(request, idtipoinmobiliaria):
    if request.method == 'GET':
        print("Lote ID:", idtipoinmobiliaria)
        lotes = Lote.objects.filter(idtipoinmobiliaria= idtipoinmobiliaria)
        serializer = LoteSerializer(lotes, many=True)
        return Response(serializer.data)


@api_view(['GET'])
def getLote(request, idinmobilaria):
    lote = Lote.objects.filter(idinmobilaria = idinmobilaria)
    serializer = LoteSerializer(lote, many=True)
    return Response(serializer.data)
 

@api_view(['POST'])
def registerLote(request):
    
    if request.method == 'POST':
        # print(request.data['precio'])
        data = {
            'idtipoinmobiliaria': request.data['idtipoinmobiliaria'],
            'idinmobilaria': request.data['idinmobilaria'],
            'nombre': request.data['nombreinmobiliaria'],
            'latitud': request.data['latitud'],
            'longitud': request.data['longitud'],
            'estado': 1,
            'descripcion': request.data['descripcion'],
            'precio': request.data['precio'],
        }
        serializer = LoteSerializer(data=data)
        if serializer.is_valid():
            lote = serializer.save()
            last_id = lote.idlote

            # ✅ Deserializa los puntos JSON
            puntos_raw = request.data.get("puntos", "[]")
            puntos_data = json.loads(puntos_raw)

            nuevos_puntos = []
            for punto in puntos_data:
                punto["idlote"] = last_id
                punto["estado"] = 1
                punto_serializer = PuntosSerializer(data=punto)
                if punto_serializer.is_valid():
                    punto_serializer.save()
                    nuevos_puntos.append(punto_serializer.data)

            # Guardar imágenes
            nuevas_imagenes = []
            imagenes_files = request.FILES.getlist('imagenes')
            for archivo in imagenes_files:
                img = {
                    'idlote': last_id,
                    'imagen': archivo
                }
                imagen_serializer = ImagenesSerializer(data=img)
                if imagen_serializer.is_valid():
                    imagen_serializer.save()
                    nuevas_imagenes.append(imagen_serializer.data)
                else:
                    return Response(imagen_serializer.errors, status=400)

            return Response({
                "inmobiliaria": serializer.data,
                "imagenes_creadas": nuevas_imagenes,
                "puntos_creados": nuevos_puntos
            }, status=201)

        return Response(serializer.errors, status=400)

@api_view(["GET"])
def rangoPrecio(request, rango):
    num1, num2 = rango.split("-")

    # Elimina comas de los números
    num1 = num1.replace(",", "")
    num2 = num2.replace(",", "")

    num1 = float(num1)

    if num2.lower() == "más":
        lote = Lote.objects.filter(precio__gte=num1)
    else:
        num2 = float(num2)
        lote = Lote.objects.filter(precio__range=(num1, num2))

    serializer = LoteSerializer(lote, many=True)
    return Response(serializer.data)

    
@api_view(['PUT'])
def deleteLote(request, idlote):
    try:
        lote = Lote.objects.get(idlote=idlote)
    except Lote.DoesNotExist:
        return Response({'error': 'Lote no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    lote.estado = 0
    lote.save()
    return Response({'message': 'Lote desactivado correctamente'}, status=status.HTTP_200_OK)
