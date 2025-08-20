from rest_framework.decorators import api_view
from rest_framework.response import Response
from ..serializers import InmobilariaSerializer, ImagenesSerializer, PuntosSerializer, TipoInmobiliariasSerializer
from ..models import Inmobilaria, Imagenes, Puntos, TipoInmobiliaria
from rest_framework import status


@api_view(['GET'])
def list_tipo_inmobiliarias(request):
    if request.method == 'GET':
        Tipoinmobiliarias = TipoInmobiliaria.objects.all()
        serializer = TipoInmobiliariasSerializer(Tipoinmobiliarias, many=True)
        return Response(serializer.data)

