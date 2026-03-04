from rest_framework.permissions import BasePermission
from api.models import Inmobiliaria, Proyecto


class IsOwnerOfLote(BasePermission):
    def has_object_permission(self, request, view, obj):
        try:
            return obj.idproyecto.idinmobiliaria.idusuario_id == request.user.idusuario
        except AttributeError:
            return False


class IsSameInmobiliaria(BasePermission):
    def has_object_permission(self, request, view, obj):
        try:
            return obj.idproyecto.idinmobiliaria_id == request.user.idinmobiliaria_id
        except AttributeError:
            return False


class IsOwnerOfProyecto(BasePermission):
    def has_object_permission(self, request, view, obj):
        usuario = request.user
        if not hasattr(usuario, "idinmobiliaria") or usuario.idinmobiliaria is None:
            return False
        return obj.idinmobiliaria_id == usuario.idinmobiliaria.idinmobiliaria


class IsSelfUser(BasePermission):
    def has_object_permission(self, request, view, obj):
        return getattr(request.user, "idusuario", None) == getattr(
            obj, "idusuario", None
        )


class IsOwnerOfInmobiliaria(BasePermission):
    def has_object_permission(self, request, view, obj):
        return getattr(obj, "idusuario_id", None) == getattr(
            request.user, "idusuario", None
        )


class IsSuperUser(BasePermission):
    def has_permission(self, request, view):
        return bool(
            getattr(request, "user", None)
            and request.user.is_authenticated
            and getattr(request.user, "is_superuser", False)
        )


def user_inmobiliaria_id(user):
    inmo = Inmobiliaria.objects.filter(idusuario=user).only("idinmobiliaria").first()
    return inmo.idinmobiliaria if inmo else None


def is_project_owned_by_user(project_id, user):
    owner_inmo_id = user_inmobiliaria_id(user)
    if not owner_inmo_id:
        return False
    return Proyecto.objects.filter(
        idproyecto=project_id, idinmobiliaria=owner_inmo_id
    ).exists()
