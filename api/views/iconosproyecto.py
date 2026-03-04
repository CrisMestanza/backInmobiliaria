from rest_framework.decorators import (
    api_view,
    permission_classes,
    authentication_classes,
)
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.authentication import CustomJWTAuthentication
from api.models import IconoProyecto
from api.serializers import IconoProyectoSerializer
from api.views.permissions import is_project_owned_by_user


@api_view(["GET"])
@permission_classes([AllowAny])
def list_iconos_disponibles(_request):
    try:
        iconos = (
            IconoProyecto.objects.filter(estado=1)
            .select_related("idicono")
            .only(
                "idiconoproyecto",
                "idproyecto_id",
                "idicono_id",
                "latitud",
                "longitud",
                "estado",
                "idicono__idiconos",
                "idicono__nombre",
                "idicono__imagen",
                "idicono__estado",
            )
        )
        serializer = IconoProyectoSerializer(iconos, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([AllowAny])
def list_iconos_proyecto(_request, idproyecto):
    try:
        iconos = (
            IconoProyecto.objects.filter(idproyecto=idproyecto, estado=1)
            .select_related("idicono")
            .only(
                "idiconoproyecto",
                "idproyecto_id",
                "idicono_id",
                "latitud",
                "longitud",
                "estado",
                "idicono__idiconos",
                "idicono__nombre",
                "idicono__imagen",
                "idicono__estado",
            )
        )
        serializer = IconoProyectoSerializer(iconos, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def add_iconos_proyecto(request):
    data = request.data
    is_many = isinstance(data, list)
    payload = data if is_many else [data]

    for item in payload:
        project_id = item.get("idproyecto")
        if not project_id or not is_project_owned_by_user(project_id, request.user):
            return Response(
                {"error": "No tienes permisos para agregar iconos a este proyecto."},
                status=status.HTTP_403_FORBIDDEN,
            )

    serializer = IconoProyectoSerializer(data=data, many=is_many)

    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # 👇 Esto hará que veas el detalle exacto del error
    print("Errores serializer:", serializer.errors)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
