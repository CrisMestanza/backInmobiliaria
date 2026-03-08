from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.views.decorators.cache import cache_page
from api.models import TipoInmobiliaria
from api.serializers import TipoInmobiliariasSerializer


@cache_page(300)
@api_view(["GET"])
@permission_classes([AllowAny])
def list_tipo_inmobiliarias(_request):
    tipo_inmobiliarias = TipoInmobiliaria.objects.all()
    serializer = TipoInmobiliariasSerializer(tipo_inmobiliarias, many=True)
    return Response(serializer.data)
