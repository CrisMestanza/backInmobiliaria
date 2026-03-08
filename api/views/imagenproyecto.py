from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.authentication import CustomJWTAuthentication
from api.file_cleanup import delete_files_and_empty_dirs
from api.models import ImagenesProyecto
from api.serializers import ImagenesProyectoSerializer
from api.views.permissions import user_inmobiliaria_id


@api_view(["GET"])
@permission_classes([AllowAny])
def list_imagen_proyecto(_request, idproyecto):
    imagenes_proyecto = ImagenesProyecto.objects.filter(idproyecto=idproyecto)
    serializer = ImagenesProyectoSerializer(imagenes_proyecto, many=True)
    return Response(serializer.data)


@api_view(["DELETE"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def delete_imagen_proyecto(request, idimagenesp):
    owner_inmo_id = user_inmobiliaria_id(request.user)
    if not owner_inmo_id:
        return Response(
            {"error": "No tienes permisos para eliminar esta imagen."},
            status=status.HTTP_403_FORBIDDEN,
        )

    imagen = (
        ImagenesProyecto.objects.select_related("idproyecto__idinmobiliaria")
        .filter(idimagenesp=idimagenesp)
        .first()
    )
    if not imagen:
        return Response(
            {"error": "Imagen de proyecto no encontrada."},
            status=status.HTTP_404_NOT_FOUND,
        )

    proyecto = imagen.idproyecto
    inmobiliaria = proyecto.idinmobiliaria if proyecto else None
    if not inmobiliaria or int(inmobiliaria.idinmobiliaria) != int(owner_inmo_id):
        return Response(
            {"error": "No tienes permisos para eliminar esta imagen."},
            status=status.HTTP_403_FORBIDDEN,
        )

    with transaction.atomic():
        file_paths = [str(imagen.imagenproyecto)] if imagen.imagenproyecto else []
        imagen.delete()
        transaction.on_commit(lambda: delete_files_and_empty_dirs(file_paths))

    return Response(
        {"message": "Imagen de proyecto eliminada correctamente."},
        status=status.HTTP_200_OK,
    )
