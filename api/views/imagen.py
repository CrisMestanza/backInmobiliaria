from django.db import transaction
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.authentication import CustomJWTAuthentication
from api.file_cleanup import delete_files_and_empty_dirs
from api.models import Imagenes
from api.serializers import ImagenesSerializer
from api.views.permissions import user_inmobiliaria_id


@api_view(["GET"])
@permission_classes([AllowAny])
def list_imagen(_request, idlote):
    imagenes = Imagenes.objects.filter(idlote=idlote)
    serializer = ImagenesSerializer(imagenes, many=True)
    return Response(serializer.data)


@api_view(["DELETE"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def delete_imagen(request, idimagenes):
    owner_inmo_id = user_inmobiliaria_id(request.user)
    if not owner_inmo_id:
        return Response(
            {"error": "No tienes permisos para eliminar esta imagen."},
            status=status.HTTP_403_FORBIDDEN,
        )

    imagen = (
        Imagenes.objects.select_related("idlote__idproyecto__idinmobiliaria")
        .filter(idimagenes=idimagenes)
        .first()
    )
    if not imagen:
        return Response(
            {"error": "Imagen no encontrada."},
            status=status.HTTP_404_NOT_FOUND,
        )

    lote = imagen.idlote
    proyecto = lote.idproyecto if lote else None
    inmobiliaria = proyecto.idinmobiliaria if proyecto else None
    if not inmobiliaria or int(inmobiliaria.idinmobiliaria) != int(owner_inmo_id):
        return Response(
            {"error": "No tienes permisos para eliminar esta imagen."},
            status=status.HTTP_403_FORBIDDEN,
        )

    with transaction.atomic():
        file_paths = [str(imagen.imagen)] if imagen.imagen else []
        imagen.delete()
        transaction.on_commit(lambda: delete_files_and_empty_dirs(file_paths))

    return Response(
        {"message": "Imagen eliminada correctamente."},
        status=status.HTTP_200_OK,
    )
