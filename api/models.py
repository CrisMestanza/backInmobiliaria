from django.db import models

   
class TipoInmobiliaria(models.Model):
    idtipoinmobiliaria = models.AutoField(primary_key=True)
    nombre = models.CharField(max_length=50, blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'tipo_inmobiliaria'

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

    class Meta:
        managed = False
        db_table = 'inmobilaria'


class Lote(models.Model):
    idlote = models.AutoField(primary_key=True)
    idtipoinmobiliaria = models.ForeignKey(TipoInmobiliaria, models.DO_NOTHING, db_column='idtipoinmobiliaria', blank=True, null=True)
    idinmobilaria = models.ForeignKey(
        Inmobilaria,
        models.DO_NOTHING,
        db_column='idinmobilaria',
        blank=True,
        null=True
    )
    nombre = models.CharField(max_length=100, blank=True, null=True)
    descripcion = models.CharField(max_length=300, blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True)
    latitud = models.CharField(max_length=45, blank=True, null=True)
    longitud = models.CharField(max_length=45, blank=True, null=True)
    precio = models.FloatField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'lote'

class Puntos(models.Model):
    idpuntos = models.AutoField(primary_key=True)
    idlote = models.ForeignKey(
        Lote,
        models.DO_NOTHING,
        db_column='idlote',
        blank=True,
        null=True
    )
    latitud = models.CharField(max_length=25, blank=True, null=True)
    longitud = models.CharField(max_length=25, blank=True, null=True)
    lado_metros = models.FloatField(blank=True, null=True)
    estado = models.IntegerField(blank=True, null=True)
    orden = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'puntos'


    class Meta:
        managed = False
        db_table = 'puntos'


class Imagenes(models.Model):
    idimagenes = models.AutoField(primary_key=True)
    idlote = models.ForeignKey(
        'Lote',
        models.DO_NOTHING,
        db_column='idlote',
        blank=True,
        null=True
    )
    imagen = models.ImageField(upload_to='inmobiliarias/')

    class Meta:
        managed = False  # Solo si estás usando tabla existente
        db_table = 'imagenes'
