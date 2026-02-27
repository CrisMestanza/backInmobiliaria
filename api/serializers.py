from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth import authenticate
from django.db import transaction
from django.contrib.auth.password_validation import validate_password
import json
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    ClickProyectos,
    ClicksContactos,
    IconoProyecto,
    Iconos,
    Imagenes,
    ImagenesProyecto,
    Inmobiliaria,
    Lote,
    Proyecto,
    Puntos,
    PuntosProyecto,
    TipoInmobiliaria,
    Usuario,
)

class InmobiliariaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Inmobiliaria
        fields = '__all__'  # O lista de campos ['id', 'nombre', 'precio']
class PuntosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Puntos
        fields = '__all__'  # O lista de campos ['id', 'nombre', 'precio']
class PuntosProyectoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PuntosProyecto
        fields = '__all__'  
class ImagenesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Imagenes
        fields = '__all__'

class ImagenesProyectoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImagenesProyecto
        fields = '__all__'
class TipoInmobiliariasSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoInmobiliaria
        fields = '__all__'
        
class ProyectoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proyecto
        fields = '__all__'
        
class LoteSerializer(serializers.ModelSerializer):
    inmobiliaria = InmobiliariaSerializer(source='idproyecto.idinmobiliaria', read_only=True)
    proyectos = ProyectoSerializer(source='idproyecto', read_only=True)
    tipoinmobiliaria = TipoInmobiliariasSerializer(source='idtipoinmobiliaria', read_only=True)

    class Meta:
        model = Lote
        fields = '__all__'

class IconosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Iconos
        fields = '__all__'  # O lista de campos ['id', 'nombre', 'precio']

class UsuarioSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Usuario
        fields = ("idusuario", "correo", "nombre", "estado", "password")
        read_only_fields = ("idusuario", "estado")

    def validate_password(self, value):
        if not value:
            return value
        if str(value).startswith("pbkdf2_"):
            return value
        validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = Usuario(**validated_data)
        user.is_staff = False
        user.is_superuser = False
        user.estado = 1
        if password:
            user.password = password if str(password).startswith("pbkdf2_") else make_password(password)
        user.save()
        return user

class ClickProyectosSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClickProyectos
        fields = '__all__'  # O lista de campos ['id', 'nombre', 'precio']
    
        
class ClicksContactosSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClicksContactos
        fields = '__all__'  # O lista de campos ['id', 'nombre', 'precio']
    


class IconoProyectoSerializer(serializers.ModelSerializer):
    idicono = serializers.PrimaryKeyRelatedField(
        queryset=Iconos.objects.all()
    )
    icono_detalle = IconosSerializer(source="idicono", read_only=True)

    class Meta:
        model = IconoProyecto
        fields = '__all__'

class PuntosProyectoMapaSerializer(serializers.ModelSerializer):
    class Meta:
        model = PuntosProyecto
        fields = ("latitud", "longitud", "orden")


class PuntosSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Puntos
        fields = ("latitud", "longitud", "orden")


class LoteMapaSerializer(serializers.ModelSerializer):
    puntos = PuntosSimpleSerializer(source="puntos_set", many=True, read_only=True)

    class Meta:
        model = Lote
        fields = (
            "idlote",
            "nombre",
            "precio",
            "vendido",
            "latitud",
            "longitud",
            "puntos",
        )


class IconoProyectoMapaSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(source="idicono.nombre", read_only=True)
    imagen = serializers.ImageField(source="idicono.imagen", read_only=True)

    class Meta:
        model = IconoProyecto
        fields = ("latitud", "longitud", "nombre", "imagen")


class ProyectoMapaSerializer(serializers.ModelSerializer):
    iconos = IconoProyectoMapaSerializer(source="iconos_proyecto", many=True, read_only=True)

    class Meta:
        model = Proyecto
        fields = (
            "idproyecto",
            "nombreproyecto",
            "latitud",
            "longitud",
            "idinmobiliaria",
            "idtipoinmobiliaria",
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
            "iconos",
        )


class ProyectoDetalleMapaSerializer(serializers.ModelSerializer):
    puntos = PuntosProyectoMapaSerializer(many=True, read_only=True)
    lotes = LoteMapaSerializer(source="lote_set", many=True, read_only=True)

    class Meta:
        model = Proyecto
        fields = ("idproyecto", "nombreproyecto", "puntos", "lotes")


class InmobiliariaRegistroSerializer(serializers.ModelSerializer):
    usuario = serializers.DictField(write_only=True)  # Entrada tipo dict
    usuario_detalle = UsuarioSerializer(source="idusuario", read_only=True)

    class Meta:
        model = Inmobiliaria
        fields = [
            'idinmobiliaria',
            'nombreinmobiliaria',
            'facebook',
            'whatsapp',
            'tiktok',
            'pagina',
            'descripcion',
            'telefono',
            'correo',
            'estado',
            'usuario',
            'usuario_detalle'
        ]

    def validate_usuario(self, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("El campo usuario debe ser un objeto JSON válido.")
        if not isinstance(value, dict):
            raise serializers.ValidationError("El campo usuario debe ser un objeto.")
        return value

    def create(self, validated_data):
        usuario_data = validated_data.pop("usuario", {}) or {}
        safe_usuario_data = {
            "correo": usuario_data.get("correo"),
            "nombre": usuario_data.get("nombre"),
            "password": usuario_data.get("password"),
            "estado": 1,
            "is_staff": False,
            "is_superuser": False,
            "is_active": True,
        }

        if not safe_usuario_data["correo"] or not safe_usuario_data["password"]:
            raise serializers.ValidationError({"usuario": "correo y password son obligatorios"})

        validate_password(safe_usuario_data["password"])
        safe_usuario_data["password"] = make_password(safe_usuario_data["password"])

        with transaction.atomic():
            usuario = Usuario.objects.create(**safe_usuario_data)
            inmobiliaria = Inmobiliaria.objects.create(idusuario=usuario, **validated_data)
        return inmobiliaria

class LoginSerializer(serializers.Serializer):
    correo = serializers.CharField()
    password = serializers.CharField()

    def validate(self, data):
        correo = data.get("correo")
        password = data.get("password")
        request = self.context.get("request")
        usuario = authenticate(request=request, username=correo, password=password)
        if not usuario:
            raise serializers.ValidationError("Credenciales inválidas")
        if not getattr(usuario, "is_active", True) or getattr(usuario, "estado", 0) != 1:
            raise serializers.ValidationError("Usuario inactivo")

        data["usuario"] = usuario
        return data
    
class CustomTokenObtainPairSerializer(serializers.Serializer):
    correo = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        correo = attrs.get("correo")
        password = attrs.get("password")

        try:
            usuario = Usuario.objects.get(correo=correo)
        except Usuario.DoesNotExist:
            raise serializers.ValidationError({"correo": "Usuario no encontrado"})

        if not check_password(password, usuario.password):
            raise serializers.ValidationError({"password": "Contrase単a incorrecta"})
        if not getattr(usuario, "is_active", True) or getattr(usuario, "estado", 0) != 1:
            raise serializers.ValidationError({"correo": "Usuario inactivo"})

        # Creamos tokens manualmente
        refresh = RefreshToken.for_user(usuario)

        data = {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "idusuario": usuario.idusuario,
            "correo": usuario.correo,
            "idinmobiliaria": getattr(usuario.inmobiliaria, "idinmobiliaria", None),
        }

        if hasattr(usuario, "inmobiliaria"):
            data["idinmobiliaria"] = usuario.inmobiliaria.idinmobiliaria

        return data

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["idusuario"] = user.idusuario
        token["correo"] = user.correo
        if hasattr(user, "inmobiliaria"):
            token["idinmobiliaria"] = user.inmobiliaria.idinmobiliaria
        return token
