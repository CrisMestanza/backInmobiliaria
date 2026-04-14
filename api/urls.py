from django.urls import path
from .views.inmobiliaria import *
from .views.auth_views import *
from .views.tipoInmobiliaria import *
from .views.imagen import *
from .views.imagenproyecto import *
from .views.lote import *
from .views.proyecto import *
from .views.usuario import *
from .views.iconos import *
from .views.iconosproyecto import *
from .views.bot import *
from .views.clicks import *
from .views.imagen360Casa import *
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

urlpatterns = [
    #Inmobiliaria 
    path('listInmobiliaria/', list_inmobiliarias),
    # path('registerInmobiliaria/', register_inmobiliaria),
    path('register_inmobiliaria/', registrar_inmobiliaria),
    path('listPuntos/<int:idlote>', list_puntos),
    path('listPuntosLoteProyecto/<int:idproyecto>/', list_puntos_por_proyecto),
    path('listPuntosProyecto/<int:idproyecto>', list_puntosproyecto),
    path('list_lote_id/<int:idlote>', list_inmobiliarias_id),
    path('getInmobiliaria/<int:idinmobiliaria>', getInmobiliaria),
    path('updateInmobiliaria/<int:idinmobiliaria>/', updateInmobiliaria),
    path('deleteInmobiliaria/<int:idinmobiliaria>/', deleteInmobiliaria),
    #Tipo  inmobiliaria 
    path('listTipoInmobiliaria/', list_tipo_inmobiliarias),
    #imagen
    path('list_imagen/<int:idlote>', list_imagen),
    path('list_imagen_proyecto/<int:idproyecto>', list_imagen_proyecto),
    path('mapa/lote_detalle/<int:idlote>/', mapa_lote_detalle),
    path('delete_imagen/<int:idimagenes>/', delete_imagen),
    path('delete_imagen_proyecto/<int:idimagenesp>/', delete_imagen_proyecto),
    
    #Lotes
    path('listLotes/', list_lotes),
    path('lote/<int:idproyecto>', lote),
    path('getLoteProyecto/<int:idproyecto>', getLote),
    path('registerLote/', registerLote),
    path('registerLotesMasivo/', registerLotesMasivo, name='register_lotes_masivo'),
    path('rangoPrecio/<str:rango>', rangoPrecio),
    path('deleteLote/<int:idlote>/', deleteLote),
    path('updateLote/<int:idlote>/', updateLote),
    path('updateLoteVendido/<int:idlote>/', updateLoteVendido),
    # urls nuevo
    path('getLotesConPuntos/<int:idproyecto>/',get_lotes_con_puntos),

    #Proyectos
    path('listProyectos/', listProyectos),
    path('mapa/proyectos/', list_proyectos_mapa),
    path('mapa/proyecto_detalle/<int:idproyecto>/', mapa_proyecto_detalle),
    path('mapa/proyecto_share/<int:idproyecto>/', mapa_proyecto_share),
    path('registerProyecto/', registerProyecto),
    path('getProyectoInmo/<int:idinmobiliaria>', getProyecto),
    path('listProyectoId/<int:idproyecto>', listProyectoId),
    path('updateProyecto/<int:idproyecto>/', updateProyecto),
    path('deleteProyecto/<int:idproyecto>/', deleteProyecto),

    #Filtrado Proyectos
    path('listProyectosInmobiliaria/<int:idinmobiliaria>/', listProyectosInmobiliaria),
    
    #Usiaros
    path('listUsuarios/', listUsuarios),
    path('registerUsuario/', registerUsuario),  
    path('listUsuarioId/<int:idusuario>', listUsuarioId),
    path('updateUsuario/<int:idusuario>/', updateUsuario),
    path('deleteUsuario/<int:idusuario>/', deleteUsuario),
    path('register_inmobiliaria_usuario/', register_inmobiliaria_usuario),
    path('login/', login_usuario),
    path('recovery/request-code/', recovery_request_code),
    path('recovery/verify-code/', recovery_verify_code),
    path('recovery/reset-password/', recovery_reset_password),
    path('activation/confirm/', confirm_account_activation),
    path('activation/resend/', resend_account_activation),
    path('logout/', logout),
    
    #Iconos
    path('listIconos/', listIconos),
    path('registerIconos/', registerIcono),
    path('listIconosId/<int:idiconos>', listIconoId),
    path('updateIconos/<int:idiconos>/', updateIcono),
    path('deleteIconos/<int:idiconos>/', deleteIcono),

    #Iconos Proyectos
    path('list_iconos_proyecto/<int:idproyecto>', list_iconos_proyecto),
    path('list_iconos_disponibles/', list_iconos_disponibles),
    path('add_iconos_proyecto/', add_iconos_proyecto),
    path('delete_icono_proyecto/<int:idiconoproyecto>/', delete_icono_proyecto),
    path('filtroCasaProyecto/<int:idtipoinmobiliaria>', tipoProyecto),
    
     # path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', refresh_token),
    path("check_auth/", CheckAuthView.as_view(), name="check_auth"),
    
    # #bot
    # path('crearBdVectorialDesdeCSVs/', crearBdVectorialDesdeCSVs),
    # path('chatBot/', chatBot),
    # path('getCasas/', getCasas),
    # path('getLotes/', getLotes),
    
    #clicks
    path('registerClickProyecto/', registerClickProyecto),
    path('registerClickContactos/', registerClickContactos),
    path('dashboard_clicks_inmobiliaria/<int:idinmobiliaria>/', dashboard_clicks_inmobiliaria),
    
    # Filtro combinados 
    path('proyectosFiltrados/', proyectos_filtrados),
    
    # imagen 360 casas
    path('guardar_imagen_360_casa/', guardar_imagenes_360_multiple),
    path('agregar_punto_recorrido/', agregar_punto_recorrido),
    path('get_imagen_360_casa/<int:idproyecto>/', get_imagenes_360_multiple)
    

    ]

