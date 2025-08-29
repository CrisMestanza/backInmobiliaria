from rest_framework.decorators import api_view
from rest_framework.response import Response
from ..serializers import InmobilariaSerializer, ImagenesSerializer, PuntosSerializer, LoteSerializer, IconosSerializer, UsuarioSerializer, ProyectoSerializer, PuntosProyectoSerializer
from ..models import Inmobilaria, Imagenes, Puntos, Lote, Iconos, Usuario, Proyecto, PuntosProyecto
from rest_framework import status
import json 

@api_view(['GET'])
def listProyectos(request):
    if request.method == 'GET':
        proyectos = Proyecto.objects.filter(estado=1)
        serializer = ProyectoSerializer(proyectos, many=True)
        return Response(serializer.data)
 

@api_view(['POST'])
def registerProyecto(request):
    if request.method == 'POST':
        data = {
            'nombreproyecto': request.data.get('nombreproyecto'),
            'longitud': request.data.get('longitud'),
            'latitud': request.data.get('latitud'),
            'idinmobilaria': request.data.get('idinmobilaria'),
            'descripcion': request.data.get('descripcion'),        
            'estado': 1,
        }
        serializer = ProyectoSerializer(data=data)
        if serializer.is_valid():
            proyecto = serializer.save()
            last_id = proyecto.idproyecto
            print(request.data)

            # ✅ Manejo flexible de puntosproyecto
            puntos_raw = request.data.get("puntos", [])
            if isinstance(puntos_raw, str):   # viene como string JSON (form-data)
                try:
                    puntos_data = json.loads(puntos_raw)
                except json.JSONDecodeError:
                    puntos_data = []
            else:  # ya viene como lista (JSON body)
                puntos_data = puntos_raw

            nuevos_puntos = []
            for idx, punto in enumerate(puntos_data):
                punto["idproyecto"] = last_id
                punto["orden"] = idx + 1
                from ..serializers import PuntosProyectoSerializer
                punto_serializer = PuntosProyectoSerializer(data=punto)
                if punto_serializer.is_valid():
                    punto_serializer.save()
                    nuevos_puntos.append(punto_serializer.data)
            print(request.data)
            return Response({
                "proyecto": serializer.data,
                "puntos_creados": nuevos_puntos
            }, status=201)

        else:
            return Response(serializer.errors, status=400)


# @api_view(['POST'])
# def registerProyecto(request):
#     if request.method == 'POST':
#         data = {
#             'nombreproyecto': request.data['nombreproyecto'],
#             'longitud': request.data['longitud'],
#             'latitud': request.data['latitud'],
#             'idinmobilaria': request.data['idinmobilaria'],
#             'descripcion': request.data['descripcion'],        
#             'estado': 1,
#         }
#         serializer = ProyectoSerializer(data=data)
#         if serializer.is_valid():
#             serializer.save()
#             print("Entro")
#             return Response(serializer.data, status=200)
#         else:
#             print("ERRORES:", serializer.errors)
#             return Response(serializer.errors, status=400)

@api_view(['GET'])
def listProyectoId(request, idproyecto):
    if request.method == 'GET':
        proyecto = Proyecto.objects.filter(idproyecto=idproyecto, estado=1)
        serializer = ProyectoSerializer(proyecto, many=True)
        return Response(serializer.data)
    
    
@api_view(['GET'])
def getProyecto(request, idinmobilaria):
    proyecto = Proyecto.objects.filter(idinmobilaria= idinmobilaria)
    serializer = ProyectoSerializer(proyecto, many=True)
    return Response(serializer.data)
 

@api_view(['PUT'])
def updateProyecto(request, idproyecto):
    try:
        proyecto = Proyecto.objects.get(idproyecto=idproyecto)
    except Proyecto.DoesNotExist:
        return Response({'error': 'InmobProyecto no encontrada'}, status=status.HTTP_404_NOT_FOUND)

    serializer = ProyectoSerializer(proyecto, data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=200)
    return Response(serializer.errors, status=400)

@api_view(['PUT'])
def deleteProyecto(request, idproyecto):
    try:
        proyecto = Proyecto.objects.get(idproyecto=idproyecto)
    except Proyecto.DoesNotExist:
        return Response({'error': 'Proyecto no encontrada'}, status=status.HTTP_404_NOT_FOUND)

    proyecto.estado = 0
    proyecto.save()
    return Response({'message': 'Proyecto desactivada correctamente'}, status=status.HTTP_200_OK)
