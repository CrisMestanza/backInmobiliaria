from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from ..serializers import *
from ..models import *
from rest_framework import status
from django.db.models import Sum
import sys
sys.stdout.reconfigure(encoding='utf-8')
# Listar iconos activos
@api_view(['POST'])
@permission_classes([AllowAny]) 
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
@permission_classes([AllowAny])  # o IsAuthenticated si usas login JWT
def dashboard_clicks_inmobiliaria(request, idinmobiliaria):
    try:
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