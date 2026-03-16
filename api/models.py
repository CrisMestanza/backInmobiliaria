import uuid
from pathlib import Path

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models


def _normalized_ext(filename):
    ext = Path(filename or "").suffix.lower()
    if ext == ".jpeg":
        return ".jpg"
    if ext in {".jpg", ".png"}:
        return ext
    return ".jpg"


def upload_proyecto_image(instance, filename):
    ext = _normalized_ext(filename)
    proyecto = getattr(instance, "idproyecto", None)
    inmobiliaria = getattr(proyecto, "idinmobiliaria", None) if proyecto else None
    if not proyecto or not inmobiliaria:
        return f"inmobiliarias/na/proyectos/na/proyecto/{uuid.uuid4().hex}{ext}"
    return (
        f"inmobiliarias/{inmobiliaria.idinmobiliaria}/proyectos/"
        f"{proyecto.idproyecto}/proyecto/{uuid.uuid4().hex}{ext}"
    )


def upload_lote_image(instance, filename):
    ext = _normalized_ext(filename)
    lote = getattr(instance, "idlote", None)
    proyecto = getattr(lote, "idproyecto", None) if lote else None
    inmobiliaria = getattr(proyecto, "idinmobiliaria", None) if proyecto else None
    if not lote or not proyecto or not inmobiliaria:
        return f"inmobiliarias/na/proyectos/na/lotes/na/{uuid.uuid4().hex}{ext}"
    return (
        f"inmobiliarias/{inmobiliaria.idinmobiliaria}/proyectos/"
        f"{proyecto.idproyecto}/lotes/{lote.idlote}/{uuid.uuid4().hex}{ext}"
    )


class Iconos(models.Model):
    idiconos = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=100)
    imagen = models.ImageField(upload_to='iconos/')
    estado = models.IntegerField(default=1)

    class Meta:
        db_table = "iconos"
        managed = True

class Imagenes(models.Model):
    idimagenes = models.AutoField(primary_key=True)
    # imagen = models.CharField(max_length=200, blank=True, null=True)
    imagen = models.ImageField(upload_to=upload_lote_image, null=True, blank=True)
    idlote = models.ForeignKey('Lote', models.DO_NOTHING, db_column='idlote', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'imagenes'

class ImagenesProyecto(models.Model):
    idimagenesp = models.AutoField(primary_key=True)
    # imagenproyecto = models.CharField(max_length=200, blank=True, null=True)
    imagenproyecto = models.ImageField(upload_to=upload_proyecto_image, null=True, blank=True)
    idproyecto = models.ForeignKey('Proyecto', models.DO_NOTHING, db_column='idproyecto', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'imagenesproyecto'


class Inmobiliaria(models.Model):
    idinmobiliaria = models.AutoField(primary_key=True)
    nombreinmobiliaria = models.CharField(db_column='nombreInmobiliaria', max_length=100, blank=True, null=True)
    facebook = models.CharField(max_length=100, blank=True, null=True)
    whatsapp = models.CharField(max_length=100, blank=True, null=True)
    tiktok = models.CharField(max_length=100, blank=True, null=True)
    pagina = models.CharField(max_length=200, blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True)
    descripcion = models.CharField(max_length=450)
    telefono = models.CharField(max_length=15)
    correo = models.CharField(max_length=50)
    idusuario = models.ForeignKey('Usuario', models.DO_NOTHING, db_column='idusuario', blank=True, null=True)


    class Meta:
        managed = False
        db_table = 'inmobiliaria'


class Lote(models.Model):
    idlote = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=200, blank=True, null=True)
    descripcion = models.CharField(max_length=2000, blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True)
    latitud = models.CharField(max_length=45, blank=True, null=True)
    longitud = models.CharField(max_length=45, blank=True, null=True)
    idtipoinmobiliaria = models.ForeignKey('TipoInmobiliaria', models.DO_NOTHING, db_column='idtipoinmobiliaria', blank=True, null=True)
    precio = models.FloatField(blank=True, null=True)
    idproyecto = models.ForeignKey('Proyecto', models.DO_NOTHING, db_column='idproyecto', blank=True, null=True)
    vendido = models.IntegerField(blank=True, null=True)
    area_total_m2 = models.CharField(max_length=60, blank=True, null=True)
    dormitorios = models.IntegerField(blank=True, null=True)
    banos = models.IntegerField(blank=True, null=True)
    cuartos = models.IntegerField(blank=True, null=True)
    titulo_propiedad = models.IntegerField(blank=True, null=True)
    cochera = models.IntegerField(blank=True, null=True)
    cocina = models.IntegerField(blank=True, null=True)
    sala = models.IntegerField(blank=True, null=True)
    patio = models.IntegerField(blank=True, null=True)
    jardin = models.IntegerField(blank=True, null=True)
    terraza = models.IntegerField(blank=True, null=True)
    azotea = models.IntegerField(blank=True, null=True)
    ancho = models.FloatField(blank=True, null=True)
    largo = models.FloatField(blank=True, null=True)
    pais = models.CharField(max_length=80, blank=True, null=True)
    bandera = models.CharField(max_length=500, blank=True, null=True)
    moneda = models.CharField(max_length=60, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'lote'



class Proyecto(models.Model):
    idproyecto = models.AutoField(primary_key=True)
    nombreproyecto = models.CharField(max_length=90, blank=True, null=True)
    longitud = models.CharField(max_length=50, blank=True, null=True)
    latitud = models.CharField(max_length=50, blank=True, null=True)
    idinmobiliaria = models.ForeignKey(Inmobiliaria, models.DO_NOTHING, db_column='idinmobiliaria', blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True)
    descripcion = models.CharField(max_length=6000, blank=True, null=True)
    idtipoinmobiliaria = models.ForeignKey('TipoInmobiliaria', models.DO_NOTHING, db_column='idtipoinmobiliaria', blank=True, null=True)
    precio = models.FloatField(blank=True, null=True)
    area_total_m2 = models.CharField(max_length=60, blank=True, null=True)
    dormitorios = models.IntegerField(blank=True, null=True)
    banos = models.IntegerField(blank=True, null=True)
    cuartos = models.IntegerField(blank=True, null=True)
    titulo_propiedad = models.IntegerField(blank=True, null=True)
    cochera = models.IntegerField(blank=True, null=True)
    cocina = models.IntegerField(blank=True, null=True)
    sala = models.IntegerField(blank=True, null=True)
    patio = models.IntegerField(blank=True, null=True)
    jardin = models.IntegerField(blank=True, null=True)
    terraza = models.IntegerField(blank=True, null=True)
    azotea = models.IntegerField(blank=True, null=True)
    ancho = models.FloatField(blank=True, null=True)
    largo = models.FloatField(blank=True, null=True)
    pais = models.CharField(max_length=80, blank=True, null=True)
    bandera = models.CharField(max_length=500, blank=True, null=True)
    moneda = models.CharField(max_length=60, blank=True, null=True)
    publico_mapa = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'proyecto'



class Puntos(models.Model):
    idpuntos = models.AutoField(primary_key=True)
    latitud = models.CharField(max_length=25, blank=True, null=True)
    longitud = models.CharField(max_length=25, blank=True, null=True)
    lado_metros = models.FloatField(blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True)
    orden = models.IntegerField(blank=True, null=True)
    idlote = models.ForeignKey(Lote, models.DO_NOTHING, db_column='idlote', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'puntos'

class PuntosProyecto(models.Model):
    idpunto = models.AutoField(primary_key=True)
    latitud = models.FloatField()
    longitud = models.FloatField()
    orden = models.IntegerField()
    idproyecto = models.ForeignKey(
        Proyecto, on_delete=models.CASCADE,
        db_column='idproyecto', related_name='puntos'
    )

    class Meta:
        db_table = 'puntosproyecto'
        managed = False

class IconoProyecto(models.Model):
    idiconoproyecto = models.AutoField(primary_key=True)
    idproyecto = models.ForeignKey(
        Proyecto,
        on_delete=models.CASCADE,
        db_column="idproyecto",
        related_name="iconos_proyecto"
    )
    idicono = models.ForeignKey(
        Iconos,
        on_delete=models.CASCADE,
        db_column="idicono",
        related_name="proyectos"
    )
    # Por si el mismo ícono debe mostrarse en distintas coordenadas dentro de un proyecto
    latitud = models.CharField(max_length=50, blank=True, null=True)
    longitud = models.CharField(max_length=50, blank=True, null=True)

    estado = models.IntegerField(blank=True, null=True, default=1)

    class Meta:
        managed = False
        db_table = "iconoproyecto"


class TipoInmobiliaria(models.Model):
    idtipoinmobiliaria = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=50, blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tipo_inmobiliaria'


class UsuarioManager(BaseUserManager):
    def create_user(self, correo, password=None, **extra_fields):
        if not correo:
            raise ValueError('El usuario debe tener un correo')
        correo = self.normalize_email(correo)
        user = self.model(correo=correo, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, correo, password, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(correo, password, **extra_fields)


class Usuario(AbstractBaseUser, PermissionsMixin):
    idusuario = models.AutoField(primary_key=True)
    correo = models.EmailField(unique=True)
    nombre = models.CharField(max_length=60, blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True, default=1)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    groups = None
    user_permissions = None

    objects = UsuarioManager()

    USERNAME_FIELD = "correo"
    REQUIRED_FIELDS = []

    class Meta:
        managed = False
        db_table = "usuario"


class PasswordResetCode(models.Model):
    idpasswordreset = models.AutoField(primary_key=True)
    idusuario = models.ForeignKey(
        Usuario,
        models.DO_NOTHING,
        db_column="idusuario",
        related_name="password_reset_codes",
    )
    codigo_hash = models.CharField(max_length=255)
    reset_token = models.CharField(max_length=120, blank=True, null=True)
    attempts = models.IntegerField(default=0)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(blank=True, null=True)
    used_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    request_ip = models.CharField(max_length=80, blank=True, null=True)

    class Meta:
        managed = True
        db_table = "password_reset_code"


class AccountActivationToken(models.Model):
    idactivationtoken = models.AutoField(primary_key=True)
    idusuario = models.ForeignKey(
        Usuario,
        models.DO_NOTHING,
        db_column="idusuario",
        related_name="activation_tokens",
    )
    token_hash = models.CharField(max_length=128, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    request_ip = models.CharField(max_length=80, blank=True, null=True)

    class Meta:
        managed = True
        db_table = "account_activation_token"

class ClicksContactos(models.Model):
    idclicksContactos = models.AutoField(primary_key=True)
    idproyecto = models.ForeignKey(
        'Proyecto',
        on_delete=models.DO_NOTHING,
        db_column='idproyecto',
        blank=True,
        null=True
    )
    dia = models.DateField(blank=True, null=True)
    hora = models.TimeField(blank=True, null=True)
    click = models.PositiveIntegerField(default=1)
    redSocial = models.CharField(max_length=45, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'clickscontactos'

class ClickProyectos(models.Model):
    idclickProyectos = models.AutoField(primary_key=True, db_column='idclickProyectos')  # ✅ corregido
    idproyecto = models.ForeignKey(
        'Proyecto',
        on_delete=models.DO_NOTHING,
        db_column='idproyecto',
        blank=True,
        null=True
    )
    fecha = models.DateField(blank=True, null=True)
    hora = models.TimeField(blank=True, null=True)
    click = models.PositiveIntegerField(default=1)

    class Meta:
        managed = False
        db_table = 'clickproyectos'


class ApiAuditLog(models.Model):
    idauditlog = models.AutoField(primary_key=True)
    event_type = models.CharField(max_length=80)
    method = models.CharField(max_length=10, blank=True, null=True)
    path = models.CharField(max_length=255, blank=True, null=True)
    status_code = models.IntegerField(blank=True, null=True)
    success = models.BooleanField(default=True)
    ip = models.CharField(max_length=80, blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True, null=True)
    idusuario = models.ForeignKey(
        Usuario,
        models.DO_NOTHING,
        db_column="idusuario",
        blank=True,
        null=True,
    )
    actor_email = models.CharField(max_length=255, blank=True, null=True)
    target_resource = models.CharField(max_length=80, blank=True, null=True)
    target_id = models.CharField(max_length=80, blank=True, null=True)
    detail = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = True
        db_table = "api_audit_log"
