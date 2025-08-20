from django.urls import path
from .views.inmobiliaria import *  # o la vista que tengas, revisa el nombre real
from .views.tipoInmobiliaria import *  # o la vista que tengas, revisa el nombre real
from .views.imagen import *  # o la vista que tengas, revisa el nombre real
from .views.lote import *  # o la vista que tengas, revisa el nombre real

urlpatterns = [
    #Inmobiliaria 
    path('listInmobiliaria/', list_inmobiliarias),
    path('registerInmobiliaria/', register_inmobilaria),
    path('listPuntos/<int:idlote>', list_puntos),
    path('list_lote_id/<int:idlote>', list_inmobiliarias_id),
    path('getImobiliaria/<int:idinmobilaria>', getImobiliaria),
    path('updateInmobiliaria/<int:idinmobilaria>/', updateInmobiliaria),
    path('deleteInmobiliaria/<int:idinmobilaria>/', deleteInmobiliaria),
    #Tipo  inmobiliaria 
    path('listTipoInmobiliaria/', list_tipo_inmobiliarias),
    #imagen
    path('list_imagen/<int:idlote>', list_imagen),
    
    #Lotes
    path('listLotes/', list_lotes),
    path('lote/<int:idtipoinmobiliaria>', lote),
    path('getLoteInmo/<int:idinmobilaria>', getLote),
    path('registerLote/', registerLote),
    path('rangoPrecio/<str:rango>', rangoPrecio), #Precios que sale en la izquierda
    path('deleteLote/<int:idlote>/', deleteLote),

    
]

