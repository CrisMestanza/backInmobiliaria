from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from ..serializers import  IconoProyectoSerializer
from ..models import IconoProyecto
from rest_framework import status
import sys
sys.stdout.reconfigure(encoding='utf-8')
@api_view(['GET'])
@permission_classes([AllowAny])
def list_iconos_disponibles(request):
    try:
        iconos = IconoProyecto.objects.all()
        serializer = IconoProyectoSerializer(iconos, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([AllowAny])
def list_iconos_proyecto(request, idproyecto):
    try:
        iconos = IconoProyecto.objects.filter(idproyecto=idproyecto, estado=1)  # solo activos
        serializer = IconoProyectoSerializer(iconos, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(['POST'])
@permission_classes([AllowAny])
def add_iconos_proyecto(request):
    data = request.data
    is_many = isinstance(data, list)

    serializer = IconoProyectoSerializer(data=data, many=is_many)

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # 👇 Esto hará que veas el detalle exacto del error
    print("Errores serializer:", serializer.errors)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

