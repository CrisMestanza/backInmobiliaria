from rest_framework.decorators import api_view
from rest_framework.response import Response
from ..serializers import InmobilariaSerializer, ImagenesSerializer, PuntosSerializer, LoteSerializer
from ..models import Inmobilaria, Imagenes, Puntos, Lote
from rest_framework import status
import json 

@api_view(['GET'])
def list_inmobiliarias(request):
    if request.method == 'GET':
        inmobiliarias = Inmobilaria.objects.all()
        serializer = InmobilariaSerializer(inmobiliarias, many=True)
        return Response(serializer.data)

@api_view(['GET'])
def list_puntos(request, idlote):
    if request.method == 'GET':
        puntos = Puntos.objects.filter(idlote=idlote) 
        serializer = PuntosSerializer(puntos, many=True)
        return Response(serializer.data)
 

@api_view(['POST'])
def register_inmobilaria(request):
    if request.method == 'POST':
        print("DATA RECIBIDA:", request.data)
        data = {
            'nombreinmobiliaria': request.data['nombreinmobiliaria'],
            'facebook': request.data['facebook'],
            'whatsapp': request.data['whatsapp'],
            'pagina': request.data['pagina'],
            'latitud': request.data['latitud'],
            'longitud': request.data['longitud'],
            'estado': 1,
            'descripcion': request.data['descripcion'],
        }
        serializer = InmobilariaSerializer(data=data)
        if serializer.is_valid():
            serializer.save()
            print("Entro")
            return Response(serializer.data, status=200)
        else:
            print("ERRORES:", serializer.errors)
            return Response(serializer.errors, status=400)

@api_view(['GET'])
def list_inmobiliarias_id(request, idlote):
    if request.method == 'GET':
        lote = Lote.objects.filter(idlote=idlote)
        serializer = LoteSerializer(lote, many=True)
        return Response(serializer.data)

@api_view(['GET'])
def getImobiliaria(request, idinmobilaria):
    inmobiliarias = Inmobilaria.objects.filter(idinmobilaria = idinmobilaria)
    serializer = InmobilariaSerializer(inmobiliarias, many=True)
    return Response(serializer.data)


@api_view(['PUT'])
def updateInmobiliaria(request, idinmobilaria):
    try:
        inmobiliaria = Inmobilaria.objects.get(idinmobilaria=idinmobilaria)
    except Inmobilaria.DoesNotExist:
        return Response({'error': 'Inmobiliaria no encontrada'}, status=status.HTTP_404_NOT_FOUND)

    serializer = InmobilariaSerializer(inmobiliaria, data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=200)
    return Response(serializer.errors, status=400)

@api_view(['PUT'])
def deleteInmobiliaria(request, idinmobilaria):
    try:
        inmobiliaria = Inmobilaria.objects.get(idinmobilaria=idinmobilaria)
    except Inmobilaria.DoesNotExist:
        return Response({'error': 'Inmobiliaria no encontrada'}, status=status.HTTP_404_NOT_FOUND)

    inmobiliaria.estado = 0
    inmobiliaria.save()
    return Response({'message': 'Inmobiliaria desactivada correctamente'}, status=status.HTTP_200_OK)
