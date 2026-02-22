from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from ..serializers import InmobiliariaSerializer, ImagenesSerializer, PuntosSerializer, TipoInmobiliariasSerializer
from ..models import Inmobiliaria, Imagenes, Puntos, TipoInmobiliaria
from rest_framework import status
import sys
sys.stdout.reconfigure(encoding='utf-8')

@api_view(['GET'])
@permission_classes([AllowAny])
def list_tipo_inmobiliarias(request):
    if request.method == 'GET':
        Tipoinmobiliarias = TipoInmobiliaria.objects.all()
        serializer = TipoInmobiliariasSerializer(Tipoinmobiliarias, many=True)
        return Response(serializer.data)