from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from api.models import Imagenes
from api.serializers import ImagenesSerializer


@api_view(["GET"])
@permission_classes([AllowAny])
def list_imagen(_request, idlote):
    imagenes = Imagenes.objects.filter(idlote=idlote)
    serializer = ImagenesSerializer(imagenes, many=True)
    return Response(serializer.data)
