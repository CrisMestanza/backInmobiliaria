from rest_framework import serializers
from .models import Imagenes, Inmobilaria, Puntos,TipoInmobiliaria, Lote, Iconos, Usuario, Proyecto

class ImagenesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Imagenes
        fields = '__all__'  # O lista de campos ['id', 'nombre', 'precio']
class InmobilariaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Inmobilaria
        fields = '__all__'  # O lista de campos ['id', 'nombre', 'precio']
class PuntosSerializer(serializers.ModelSerializer):
    class Meta:
        model = Puntos
        fields = '__all__'  # O lista de campos ['id', 'nombre', 'precio']
class ImagenesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Imagenes
        fields = '__all__'
class TipoInmobiliariasSerializer(serializers.ModelSerializer):
    class Meta:
        model = TipoInmobiliaria
        fields = '__all__'
class LoteSerializer(serializers.ModelSerializer):
    inmobiliaria = InmobilariaSerializer(source='idinmobilaria', read_only=True)
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
        fields = '__all__'  # O lista de campos ['id', 'nombre', 'precio']

class ProyectoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Proyecto
        fields = '__all__'  # O lista de campos ['id', 'nombre', 'precio']