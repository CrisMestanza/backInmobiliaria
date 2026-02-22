from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from ..serializers import  ImagenesProyectoSerializer
from ..models import Inmobiliaria, ImagenesProyecto
from rest_framework import status
import sys
sys.stdout.reconfigure(encoding='utf-8')

@api_view(['GET'])
@permission_classes([AllowAny])
def list_imagen_proyecto(request, idproyecto):
    if request.method == 'GET':
        Tipoinmobiliarias = ImagenesProyecto.objects.filter(idproyecto= idproyecto)
        serializer = ImagenesProyectoSerializer(Tipoinmobiliarias, many=True)
        return Response(serializer.data)