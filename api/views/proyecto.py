import json

from django.db import transaction
from django.db.models import Prefetch
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.authentication import CustomJWTAuthentication
from api.models import (
    ClickProyectos,
    ClicksContactos,
    IconoProyecto,
    Imagenes,
    ImagenesProyecto,
    Inmobiliaria,
    Lote,
    Proyecto,
    Puntos,
    PuntosProyecto,
)
from api.serializers import (
    ProyectoDetalleMapaSerializer,
    ProyectoMapaSerializer,
    ProyectoSerializer,
)
from api.views.permissions import IsOwnerOfProyecto, user_inmobiliaria_id
from api.security_uploads import build_secure_image_name, validate_uploaded_image

PROYECTO_MAP_ONLY_FIELDS = (
    "idproyecto",
    "nombreproyecto",
    "latitud",
    "longitud",
    "idinmobiliaria_id",
    "idtipoinmobiliaria_id",
    "estado",
    "descripcion",
    "precio",
    "area_total_m2",
    "dormitorios",
    "banos",
    "cuartos",
    "titulo_propiedad",
    "cochera",
    "cocina",
    "sala",
    "patio",
    "jardin",
    "terraza",
    "azotea",
    "ancho",
    "largo",
)


def _parse_json_list(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return value if isinstance(value, list) else []


@api_view(["GET"])
@permission_classes([AllowAny])
def listProyectos(_request):
    proyectos = (
        Proyecto.objects.filter(estado=1)
        .only(*PROYECTO_MAP_ONLY_FIELDS)
        .prefetch_related(
            Prefetch(
                "iconos_proyecto",
                queryset=IconoProyecto.objects.filter(estado=1)
                .select_related("idicono")
                .only(
                    "idproyecto_id",
                    "latitud",
                    "longitud",
                    "idicono__nombre",
                    "idicono__imagen",
                ),
            )
        )
    )
    serializer = ProyectoMapaSerializer(proyectos, many=True)
    return Response(serializer.data)


@api_view(["POST"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def registerProyecto(request):
    inmobiliaria_usuario = (
        Inmobiliaria.objects.filter(idusuario=request.user)
        .only("idinmobiliaria")
        .first()
    )
    if not inmobiliaria_usuario:
        return Response(
            {"error": "Usuario sin inmobiliaria asociada"},
            status=status.HTTP_403_FORBIDDEN,
        )

    data = {
        "nombreproyecto": request.data.get("nombreproyecto"),
        "longitud": request.data.get("longitud"),
        "latitud": request.data.get("latitud"),
        "idinmobiliaria": inmobiliaria_usuario.idinmobiliaria,
        "descripcion": request.data.get("descripcion"),
        "idtipoinmobiliaria": request.data.get("idtipoinmobiliaria"),
        "estado": 1,
        "dormitorios": request.data.get("dormitorios", 0),
        "banos": request.data.get("banos", 0),
        "cuartos": request.data.get("cuartos", 0),
        "titulo_propiedad": request.data.get("titulo_propiedad", 0),
        "cochera": request.data.get("cochera", 0),
        "cocina": request.data.get("cocina", 0),
        "sala": request.data.get("sala", 0),
        "patio": request.data.get("patio", 0),
        "jardin": request.data.get("jardin", 0),
        "terraza": request.data.get("terraza", 0),
        "azotea": request.data.get("azotea", 0),
        "precio": request.data.get("precio", 0),
        "area_total_m2": request.data.get("area_total_m2", 0),
        "ancho": request.data.get("ancho", 0),
        "largo": request.data.get("largo", 0),
    }

    serializer = ProyectoSerializer(data=data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    puntos_data = _parse_json_list(request.data.get("puntos", []))

    with transaction.atomic():
        proyecto = serializer.save()

        puntos_bulk = []
        for idx, punto in enumerate(puntos_data):
            lat = punto.get("latitud", punto.get("lat"))
            lng = punto.get("longitud", punto.get("lng"))
            if lat is None or lng is None:
                continue
            puntos_bulk.append(
                PuntosProyecto(
                    idproyecto=proyecto,
                    latitud=lat,
                    longitud=lng,
                    orden=idx + 1,
                )
            )
        if puntos_bulk:
            PuntosProyecto.objects.bulk_create(puntos_bulk, batch_size=500)

        nuevas_imagenes = []
        for img in request.FILES.getlist("imagenes"):
            validate_uploaded_image(img)
            img.name = build_secure_image_name(
                inmobiliaria_id=inmobiliaria_usuario.idinmobiliaria,
                proyecto_id=proyecto.idproyecto,
                image_type="proyecto",
                original_name=img.name,
            )
            imagen_obj = ImagenesProyecto.objects.create(
                idproyecto=proyecto, imagenproyecto=img
            )
            nuevas_imagenes.append(
                {
                    "idimagenesp": imagen_obj.idimagenesp,
                    "imagenproyecto": imagen_obj.imagenproyecto.url,
                    "idproyecto": proyecto.idproyecto,
                }
            )

    return Response(
        {
            "proyecto": serializer.data,
            "puntos_creados": len(puntos_bulk),
            "imagenes_creadas": nuevas_imagenes,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def listProyectoId(_request, idproyecto):
    proyecto = (
        Proyecto.objects.filter(idproyecto=idproyecto, estado=1)
        .only("idproyecto", "nombreproyecto")
        .prefetch_related(
            Prefetch(
                "puntos",
                queryset=PuntosProyecto.objects.only(
                    "idproyecto_id", "latitud", "longitud", "orden"
                ).order_by("orden"),
            ),
            Prefetch(
                "lote_set",
                queryset=Lote.objects.only(
                    "idlote",
                    "nombre",
                    "precio",
                    "vendido",
                    "latitud",
                    "longitud",
                    "idproyecto_id",
                ).prefetch_related(
                    Prefetch(
                        "puntos_set",
                        queryset=Puntos.objects.only(
                            "idlote_id", "latitud", "longitud", "orden"
                        ).order_by("orden"),
                    )
                ),
            ),
        )
        .first()
    )
    if not proyecto:
        return Response(
            {"error": "Proyecto no encontrado"}, status=status.HTTP_404_NOT_FOUND
        )

    serializer = ProyectoDetalleMapaSerializer(proyecto)
    return Response(serializer.data)


@api_view(["GET"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def getProyecto(request, idinmobiliaria):
    owner_inmo_id = user_inmobiliaria_id(request.user)
    if not owner_inmo_id or int(idinmobiliaria) != int(owner_inmo_id):
        return Response(
            {"error": "No tienes permisos para ver estos proyectos."},
            status=status.HTTP_403_FORBIDDEN,
        )

    proyecto = Proyecto.objects.filter(idinmobiliaria=idinmobiliaria)
    serializer = ProyectoSerializer(proyecto, many=True)
    return Response(serializer.data)


@api_view(["PUT"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated, IsOwnerOfProyecto])
def updateProyecto(request, idproyecto):
    try:
        proyecto = Proyecto.objects.get(idproyecto=idproyecto)
    except Proyecto.DoesNotExist:
        return Response(
            {"error": "Proyecto no encontrado"}, status=status.HTTP_404_NOT_FOUND
        )

    inmobiliaria_usuario = Inmobiliaria.objects.filter(idusuario=request.user).first()
    if (
        not inmobiliaria_usuario
        or proyecto.idinmobiliaria_id != inmobiliaria_usuario.idinmobiliaria
    ):
        return Response(
            {"error": "No tienes permisos para editar este proyecto."},
            status=status.HTTP_403_FORBIDDEN,
        )

    serializer = ProyectoSerializer(proyecto, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_200_OK)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["DELETE"])
@authentication_classes([CustomJWTAuthentication])
@permission_classes([IsAuthenticated])
def deleteProyecto(request, idproyecto):
    try:
        proyecto = Proyecto.objects.filter(idproyecto=idproyecto).first()
        if not proyecto:
            return Response(
                {"error": "Proyecto no encontrado."}, status=status.HTTP_404_NOT_FOUND
            )

        inmobiliaria_usuario = Inmobiliaria.objects.filter(
            idusuario=request.user
        ).first()
        if not inmobiliaria_usuario:
            return Response(
                {"error": "El usuario no tiene una inmobiliaria asociada."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if proyecto.idinmobiliaria_id != inmobiliaria_usuario.idinmobiliaria:
            return Response(
                {"error": "No tienes permisos para eliminar este proyecto."},
                status=status.HTTP_403_FORBIDDEN,
            )

        with transaction.atomic():
            # 🔹 Eliminar primero relaciones dependientes
            ClickProyectos.objects.filter(idproyecto=idproyecto).delete()
            ClicksContactos.objects.filter(idproyecto=idproyecto).delete()
            Puntos.objects.filter(idlote__idproyecto=idproyecto).delete()
            Imagenes.objects.filter(idlote__idproyecto=idproyecto).delete()
            Lote.objects.filter(idproyecto=idproyecto).delete()
            ImagenesProyecto.objects.filter(idproyecto=idproyecto).delete()
            PuntosProyecto.objects.filter(idproyecto=idproyecto).delete()
            proyecto.delete()

        return Response(
            {"message": "Proyecto y todas sus relaciones eliminadas correctamente."},
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        return Response(
            {"error": f"Ocurrió un error al eliminar el proyecto: {str(e)}"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def tipoProyecto(_request, idtipoinmobiliaria):
    tipo = (
        Proyecto.objects.filter(estado=1, idtipoinmobiliaria=idtipoinmobiliaria)
        .only(*PROYECTO_MAP_ONLY_FIELDS)
        .prefetch_related(
            Prefetch(
                "iconos_proyecto",
                queryset=IconoProyecto.objects.filter(estado=1)
                .select_related("idicono")
                .only(
                    "idproyecto_id",
                    "latitud",
                    "longitud",
                    "idicono__nombre",
                    "idicono__imagen",
                ),
            )
        )
    )
    serializer = ProyectoMapaSerializer(tipo, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def listProyectosInmobiliaria(_request, idinmobiliaria):
    proyectos = Proyecto.objects.filter(idinmobiliaria=idinmobiliaria, estado=1)
    serializer = ProyectoSerializer(proyectos, many=True)
    return Response(serializer.data)


@api_view(["GET"])
@permission_classes([AllowAny])
def proyectos_filtrados(request):
    tipo = request.GET.get("tipo")  # idtipoinmobiliaria
    rango = request.GET.get("rango")  # 15001-35000
    inmo = request.GET.get("inmo")  # opcional

    proyectos = (
        Proyecto.objects.filter(estado=1)
        .only(*PROYECTO_MAP_ONLY_FIELDS)
        .prefetch_related(
            Prefetch(
                "iconos_proyecto",
                queryset=IconoProyecto.objects.filter(estado=1)
                .select_related("idicono")
                .only(
                    "idproyecto_id",
                    "latitud",
                    "longitud",
                    "idicono__nombre",
                    "idicono__imagen",
                ),
            )
        )
    )

    if tipo:
        proyectos = proyectos.filter(idtipoinmobiliaria=tipo)

    if inmo:
        proyectos = proyectos.filter(idinmobiliaria=inmo)

    if rango:
        try:
            min_p, max_p = map(float, rango.split("-"))
            proyectos = proyectos.filter(lote__precio__range=(min_p, max_p)).distinct()
        except ValueError:
            pass

    serializer = ProyectoMapaSerializer(proyectos, many=True)
    return Response(serializer.data)
