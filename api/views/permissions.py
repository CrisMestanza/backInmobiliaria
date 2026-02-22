from rest_framework.permissions import BasePermission

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