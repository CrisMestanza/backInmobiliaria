from rest_framework.decorators import api_view, permission_classes, authentication_classes, throttle_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from ..serializers import *
from ..models import *
from rest_framework import status
from django.db.models import Sum
from ..authentication import CustomJWTAuthentication
from ..throttling import ClickRateThrottle
from .permissions import user_inmobiliaria_id
import sys
sys.stdout.reconfigure(encoding='utf-8')
# Listar iconos activos
@api_view(['POST'])
@permission_classes([AllowAny]) 
@throttle_classes([ClickRateThrottle])
def registerClickProyecto(request):
    data = {
        'idproyecto': request.data.get('idproyecto'),
        'fecha': request.data.get('fecha'),
        'hora': request.data.get('hora'),
        'click': 1
    }
    serializer = ClickProyectosSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny]) 
@throttle_classes([ClickRateThrottle])
def registerClickContactos(request):
    data = {
        'idproyecto': request.data.get('idproyecto'),
        'dia': request.data.get('dia'),
        'hora': request.data.get('hora'),
        'click': 1,
        'redSocial': request.data.get('redSocial'),
    }
    serializer = ClicksContactosSerializer(data=data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

# Mostrar datos 
@api_view(['GET'])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def dashboard_clicks_inmobiliaria(request, idinmobiliaria):
    try:
        owner_inmo_id = user_inmobiliaria_id(request.user)
        if not owner_inmo_id or int(idinmobiliaria) != int(owner_inmo_id):
            return Response({"error": "No tienes permisos para ver este dashboard."}, status=403)

        # 🔹 Obtener los proyectos de la inmobiliaria
        proyectos = Proyecto.objects.filter(idinmobiliaria=idinmobiliaria)
        if not proyectos.exists():
            return Response({
                "total_clicks_contactos": 0,
                "total_clicks_proyectos": 0,
                "detalle_contactos": []
            })

        # 🧩 Total de clics en Contactos
        total_clicks_contactos = (
            ClicksContactos.objects.filter(idproyecto__in=proyectos)
            .aggregate(total=Sum('click'))
            .get('total') or 0
        )

        # 🧩 Total de clics en Proyectos
        total_clicks_proyectos = (
            ClickProyectos.objects.filter(idproyecto__in=proyectos)
            .aggregate(total=Sum('click'))
            .get('total') or 0
        )

        # 🧩 Detalle por redSocial
        detalle_contactos = (
            ClicksContactos.objects.filter(idproyecto__in=proyectos)
            .values('redSocial')
            .annotate(total=Sum('click'))
        )

        # 🔹 Armar respuesta
        return Response({
            "total_clicks_contactos": total_clicks_contactos,
            "total_clicks_proyectos": total_clicks_proyectos,
            "detalle_contactos": list(detalle_contactos)
        })

    except Exception as e:
        return Response({"error": str(e)}, status=500)
