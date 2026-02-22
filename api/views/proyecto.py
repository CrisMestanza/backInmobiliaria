from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from ..serializers import InmobiliariaSerializer, ImagenesSerializer, PuntosSerializer, LoteSerializer, IconosSerializer, UsuarioSerializer, ProyectoSerializer, PuntosProyectoSerializer
from ..models import Inmobiliaria, Imagenes, Puntos, Lote, Iconos, Usuario, Proyecto, PuntosProyecto, ImagenesProyecto
from django.db import transaction
from rest_framework import status
import json
from rest_framework.decorators import authentication_classes
from ..authentication import CustomJWTAuthentication
from .permissions import IsOwnerOfProyecto, IsSameInmobiliaria
from rest_framework.permissions import IsAuthenticated
import sys
sys.stdout.reconfigure(encoding='utf-8')

@api_view(['GET'])
@permission_classes([AllowAny])
def listProyectos(request):
    if request.method == 'GET':
        proyectos = Proyecto.objects.filter(estado=1)
        serializer = ProyectoSerializer(proyectos, many=True)
        return Response(serializer.data)
 
@api_view(['POST'])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def registerProyecto(request):
    if request.method == 'POST':
        data = {
            'nombreproyecto': request.data.get('nombreproyecto'),
            'longitud': request.data.get('longitud'),
            'latitud': request.data.get('latitud'),
            'idinmobiliaria': request.data.get('idinmobiliaria'),
            'descripcion': request.data.get('descripcion'),
            'idtipoinmobiliaria': request.data.get('idtipoinmobiliaria'),
            'estado': 1,
        
            # CAMPOS QUE FALTABAN
            'dormitorios': request.data.get('dormitorios', 0),
            'banos': request.data.get('banos', 0),
            'cuartos': request.data.get('cuartos', 0),
            'titulo_propiedad': request.data.get('titulo_propiedad', 0),
            'cochera': request.data.get('cochera', 0),
            'cocina': request.data.get('cocina', 0),
            'sala': request.data.get('sala', 0),
            'patio': request.data.get('patio', 0),
            'jardin': request.data.get('jardin', 0),
            'terraza': request.data.get('terraza', 0),
            'azotea': request.data.get('azotea', 0),
            'precio': request.data.get('precio', 0),
            'area_total_m2': request.data.get('area_total_m2', 0),
            'ancho': request.data.get('ancho', 0),
            'largo': request.data.get('largo', 0),
        }

        serializer = ProyectoSerializer(data=data)
        if serializer.is_valid():
            proyecto = serializer.save()
            last_id = proyecto.idproyecto
            print("Datos recibidos:", request.data)

            puntos_raw = request.data.get("puntos", [])
            if isinstance(puntos_raw, str):
                try:
                    puntos_data = json.loads(puntos_raw)
                except json.JSONDecodeError:
                    puntos_data = []
            else:
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

            imagenes = request.FILES.getlist("imagenes")
            nuevas_imagenes = []
            from ..models import ImagenesProyecto
            for img in imagenes:
                imagen_obj = ImagenesProyecto.objects.create(
                    idproyecto=proyecto,
                    imagenproyecto=img
                )
                nuevas_imagenes.append({
                    "idimagenesp": imagen_obj.idimagenesp,
                    "imagenproyecto": imagen_obj.imagenproyecto.url,
                    "idproyecto": last_id
                })

            return Response({
                "proyecto": serializer.data,
                "puntos_creados": nuevos_puntos,
                "imagenes_creadas": nuevas_imagenes
            }, status=201)

        else:
            return Response(serializer.errors, status=400)


@api_view(['GET'])
@permission_classes([AllowAny])
def listProyectoId(request, idproyecto):
    if request.method == 'GET':
        proyecto = Proyecto.objects.filter(idproyecto=idproyecto, estado=1)
        serializer = ProyectoSerializer(proyecto, many=True)
        return Response(serializer.data)
    
    
@api_view(['GET'])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([AllowAny])
def getProyecto(request, idinmobiliaria):
    proyecto = Proyecto.objects.filter(idinmobiliaria= idinmobiliaria)
    serializer = ProyectoSerializer(proyecto, many=True)
    return Response(serializer.data)
 

@api_view(['PUT'])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated, IsOwnerOfProyecto])
def updateProyecto(request, idproyecto):
    try:
        proyecto = Proyecto.objects.get(idproyecto=idproyecto)
    except Proyecto.DoesNotExist:
        return Response({'error': 'Proyecto no encontrado'}, status=status.HTTP_404_NOT_FOUND)

    inmobiliaria_usuario = Inmobiliaria.objects.filter(idusuario=request.user).first()
    if not inmobiliaria_usuario or proyecto.idinmobiliaria_id != inmobiliaria_usuario.idinmobiliaria:
        return Response({"error": "No tienes permisos para editar este proyecto."},
                    status=status.HTTP_403_FORBIDDEN)

    serializer = ProyectoSerializer(proyecto, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

from ..models import ClickProyectos, ClicksContactos

@api_view(['DELETE'])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def deleteProyecto(request, idproyecto):
    try:
        proyecto = Proyecto.objects.filter(idproyecto=idproyecto).first()
        if not proyecto:
            return Response({"error": "Proyecto no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        inmobiliaria_usuario = Inmobiliaria.objects.filter(idusuario=request.user).first()
        if not inmobiliaria_usuario:
            return Response({"error": "El usuario no tiene una inmobiliaria asociada."},
                            status=status.HTTP_403_FORBIDDEN)

        if proyecto.idinmobiliaria_id != inmobiliaria_usuario.idinmobiliaria:
            return Response({"error": "No tienes permisos para eliminar este proyecto."},
                            status=status.HTTP_403_FORBIDDEN)

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

        return Response({
            "message": "Proyecto y todas sus relaciones eliminadas correctamente."
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response(
            {"error": f"Ocurrió un error al eliminar el proyecto: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )


@api_view(['GET'])
@permission_classes([AllowAny])
def tipoProyecto(request, idtipoinmobiliaria):
    if request.method == 'GET':
        tipo = Proyecto.objects.filter(estado=1,idtipoinmobiliaria= idtipoinmobiliaria )
        serializer = ProyectoSerializer(tipo, many=True)
        return Response(serializer.data)
    
@api_view(['GET'])
@permission_classes([AllowAny])
def listProyectosInmobiliaria(request, idinmobiliaria):
    if request.method == 'GET':
        proyectos = Proyecto.objects.filter(idinmobiliaria=idinmobiliaria, estado=1)
        serializer = ProyectoSerializer(proyectos, many=True)
        return Response(serializer.data)
        
        
@api_view(['GET'])
@permission_classes([AllowAny])
def proyectos_filtrados(request):
    tipo = request.GET.get('tipo')        # idtipoinmobiliaria
    rango = request.GET.get('rango')      # 15001-35000
    inmo  = request.GET.get('inmo')       # opcional

    proyectos = Proyecto.objects.filter(estado=1)

    if tipo:
        proyectos = proyectos.filter(idtipoinmobiliaria=tipo)

    if inmo:
        proyectos = proyectos.filter(idinmobiliaria=inmo)

    if rango:
        try:
            min_p, max_p = map(float, rango.split("-"))
            proyectos = proyectos.filter(
                lote__precio__gte=min_p,
                lote__precio__lte=max_p
            ).distinct()
        except:
            pass

    serializer = ProyectoSerializer(proyectos, many=True)
    return Response(serializer.data)
