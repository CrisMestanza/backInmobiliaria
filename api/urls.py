from django.urls import path
from .views.inmobiliaria import *  # o la vista que tengas, revisa el nombre real
from .views.tipoInmobiliaria import *  # o la vista que tengas, revisa el nombre real
from .views.imagen import *  # o la vista que tengas, revisa el nombre real
from .views.lote import *  # o la vista que tengas, revisa el nombre real
from .views.proyecto import *  # o la vista que tengas, revisa el nombre real
from .views.usuario import *  # o la vista que tengas, revisa el nombre real
from .views.iconos import *  # o la vista que tengas, revisa el nombre real

urlpatterns = [
    #Inmobiliaria 
    path('listInmobiliaria/', list_inmobiliarias),
    path('registerInmobiliaria/', register_inmobilaria),
    path('listPuntos/<int:idlote>', list_puntos),
    path('listPuntosProyecto/<int:idproyecto>', list_puntosproyecto),
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
    path('lote/<int:idproyecto>', lote),
    path('getLoteProyecto/<int:idproyecto>', getLote),
    path('registerLote/', registerLote),
    path('rangoPrecio/<str:rango>', rangoPrecio),
    path('deleteLote/<int:idlote>/', deleteLote),

    #Proyectos
    path('listProyectos/', listProyectos),
    path('registerProyecto/', registerProyecto),
    path('getProyectoInmo/<int:idinmobilaria>', getProyecto),
    path('listProyectoId/<int:idproyecto>', listProyectoId),
    path('updateProyecto/<int:idproyecto>/', updateProyecto),
    path('deleteProyecto/<int:idproyecto>/', deleteProyecto),
    
    #Usiaros
    path('listUsuarios/', listUsuarios),
    path('registerUsuario/', registerUsuario),  
    path('listUsuarioId/<int:idusuario>', listUsuarioId),
    path('updateUsuario/<int:idusuario>/', updateUsuario),
    path('deleteUsuario/<int:idusuario>/', deleteUsuario),
    path('loginUsuario/', loginUsuario), #Login
    
    #Iconos
    path('listIconos/', listIconos),
    path('registerIconos/', registerIcono),
    path('listIconosId/<int:idiconos>', listIconoId),
    path('updateIconos/<int:idiconos>/', updateIcono),
    path('deleteIconos/<int:idiconos>/', deleteIcono),
    
    ]

