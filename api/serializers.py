from rest_framework import serializers
from django.contrib.auth.hashers import make_password,check_password
from .models import Imagenes, Inmobiliaria, Puntos, PuntosProyecto,TipoInmobiliaria, Lote, Iconos, Usuario, Proyecto, ImagenesProyecto, IconoProyecto, ClickProyectos, ClicksContactos
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from rest_framework_simplejwt.tokens import RefreshToken

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
        fields = '__all__'  # O lista de campos ['id', 'nombre', 'precio']
        
class LoteSerializer(serializers.ModelSerializer):
    inmobiliaria = InmobiliariaSerializer(source='idinmobiliaria', read_only=True)
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
    class Meta:
        model = Usuario
        exclude = ['password']

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

    def create(self, validated_data):
        usuario_data = validated_data.pop('usuario')
        if "password" in usuario_data:
            usuario_data["password"] = make_password(usuario_data["password"])
        usuario = Usuario.objects.create(**usuario_data)
        inmobiliaria = Inmobiliaria.objects.create(idusuario=usuario, **validated_data)

        return inmobiliaria

class LoginSerializer(serializers.Serializer):
    correo = serializers.CharField()
    password = serializers.CharField()

    def validate(self, data):
        from django.contrib.auth.hashers import check_password
        from .models import Usuario

        correo = data.get("correo")
        password = data.get("password")

        try:
            usuario = Usuario.objects.get(correo=correo)
        except Usuario.DoesNotExist:
            raise serializers.ValidationError("Usuario no encontrado")

        if not check_password(password, usuario.password):
            raise serializers.ValidationError("Contrase単a incorrecta")

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
        
        
# serializers.py

class PuntosSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Puntos
        fields = ('latitud', 'longitud')


class LoteMapaSerializer(serializers.ModelSerializer):
    puntos = PuntosSimpleSerializer(source='puntos_set', many=True)

    class Meta:
        model = Lote
        fields = '__all__'
