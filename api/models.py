from django.db import models

class Iconos(models.Model):
    idiconos = models.AutoField(primary_key=True)
    nombreicono = models.CharField(max_length=45, blank=True, null=True)
    longitud = models.CharField(max_length=60, blank=True, null=True)
    latitud = models.CharField(max_length=60, blank=True, null=True)
    idproyecto = models.IntegerField(blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True)
    class Meta:
        managed = False
        db_table = 'iconos'


class Imagenes(models.Model):
    idimagenes = models.AutoField(primary_key=True)
    imagen = models.CharField(max_length=200, blank=True, null=True)
    idlote = models.ForeignKey('Lote', models.DO_NOTHING, db_column='idlote', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'imagenes'


class Inmobilaria(models.Model):
    idinmobilaria = models.AutoField(primary_key=True)
    nombreinmobiliaria = models.CharField(db_column='nombreInmobiliaria', max_length=200, blank=True, null=True)  # Field name made lowercase.
    facebook = models.CharField(max_length=200, blank=True, null=True)
    whatsapp = models.CharField(max_length=200, blank=True, null=True)
    pagina = models.CharField(max_length=200, blank=True, null=True)
    latitud = models.CharField(max_length=25, blank=True, null=True)
    longitud = models.CharField(max_length=25, blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True)
    descripcion = models.CharField(max_length=450, blank=True, null=True)
    idusuario = models.ForeignKey('Usuario', models.DO_NOTHING, db_column='idusuario', blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'inmobilaria'


class Lote(models.Model):
    idlote = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=200, blank=True, null=True)
    descripcion = models.CharField(max_length=250, blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True)
    latitud = models.CharField(max_length=45, blank=True, null=True)
    longitud = models.CharField(max_length=45, blank=True, null=True)
    idtipoinmobiliaria = models.ForeignKey('TipoInmobiliaria', models.DO_NOTHING, db_column='idtipoinmobiliaria', blank=True, null=True)
    precio = models.FloatField(blank=True, null=True)
    idproyecto = models.ForeignKey('Proyecto', models.DO_NOTHING, db_column='idproyecto', blank=True, null=True)
    vendido = models.IntegerField(blank=True, null=True)
    class Meta:
        managed = False
        db_table = 'lote'


class Proyecto(models.Model):
    idproyecto = models.AutoField(primary_key=True)
    nombreproyecto = models.CharField(max_length=90, blank=True, null=True)
    longitud = models.CharField(max_length=50, blank=True, null=True)
    latitud = models.CharField(max_length=50, blank=True, null=True)
    idinmobilaria = models.ForeignKey(Inmobilaria, models.DO_NOTHING, db_column='idinmobilaria', blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True)
    descripcion = models.CharField(max_length=450, blank=True, null=True)
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


class TipoInmobiliaria(models.Model):
    idtipoinmobiliaria = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=50, blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tipo_inmobiliaria'


class Usuario(models.Model):
    idusuario = models.AutoField(primary_key=True)
    correo = models.CharField(max_length=70, blank=True, null=True)
    contrasena = models.CharField(max_length=45, blank=True, null=True)
    nombre = models.CharField(max_length=60, blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True)
    class Meta:
        managed = False
        db_table = 'usuario'