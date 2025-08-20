from rest_framework import serializers
from .models import Imagenes, Inmobilaria, Puntos,TipoInmobiliaria, Lote

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
