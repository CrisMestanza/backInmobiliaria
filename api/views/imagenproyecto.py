from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from api.models import ImagenesProyecto
from api.serializers import ImagenesProyectoSerializer


@api_view(["GET"])
@permission_classes([AllowAny])
def list_imagen_proyecto(_request, idproyecto):
    imagenes_proyecto = ImagenesProyecto.objects.filter(idproyecto=idproyecto)
    serializer = ImagenesProyectoSerializer(imagenes_proyecto, many=True)
    return Response(serializer.data)
