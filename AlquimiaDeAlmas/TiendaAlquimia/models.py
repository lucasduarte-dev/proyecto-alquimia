from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.humanize.templatetags.humanize import intcomma

# Modelo de perfil para almacenar micorreo_customer_id y datos de contacto/dirección
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    micorreo_customer_id = models.CharField(max_length=20, blank=True, null=True)
    document_id = models.CharField(max_length=20, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    street_name = models.CharField(max_length=100, blank=True, null=True)
    street_number = models.CharField(max_length=20, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    province_code = models.CharField(max_length=2, blank=True, null=True)
    postal_code = models.CharField(max_length=10, blank=True, null=True)

    def __str__(self):
        return f"Perfil de {self.user.username}"

class CategoriaProducto(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.nombre

class Producto(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField()
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    imagen = models.ImageField(upload_to='productos/')
    imagen2 = models.ImageField(upload_to='productos/', blank=True, null=True)
    stock = models.IntegerField()
    categoria = models.ForeignKey(CategoriaProducto, on_delete=models.CASCADE, related_name='productos')
    peso_gramos = models.IntegerField(default=1000)  # Peso en gramos
    alto_cm = models.IntegerField(default=10)       # Alto en cm
    ancho_cm = models.IntegerField(default=20)      # Ancho en cm
    largo_cm = models.IntegerField(default=30)      # Largo en cm

    def __str__(self):
        return self.nombre
    
    def precio_formateado(self):
        partes = f"{self.precio:.2f}".split(".")
        parte_entera = intcomma(int(partes[0]))
        return f"{parte_entera},{partes[1]}"

class Curso(models.Model):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField()
    precio = models.DecimalField(max_digits=10, decimal_places=2)
    imagen = models.ImageField(upload_to='cursos/', blank=True, null=True)

    def __str__(self):
        return self.nombre
    
    def precio_formateado(self):
        partes = f"{self.precio:.2f}".split(".")
        parte_entera = intcomma(int(partes[0]))
        return f"{parte_entera},{partes[1]}"

class Carrito(models.Model):
    usuario = models.OneToOneField(User, on_delete=models.CASCADE, related_name='carrito')
    creado = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Carrito de {self.usuario.username}"

class ItemCarrito(models.Model):
    carrito = models.ForeignKey(Carrito, on_delete=models.CASCADE, related_name='items')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    contenido = GenericForeignKey('content_type', 'object_id')
    cantidad = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.cantidad} x {self.contenido}"

    def subtotal(self):
        return self.cantidad * self.contenido.precio
    
    def precio_formateado(self):
        subtotal = self.subtotal()
        partes = f"{subtotal:.2f}".split(".")
        parte_entera = intcomma(int(partes[0]))
        return f"{parte_entera},{partes[1]}"

    def total(self):
        return sum(item.subtotal() for item in self.items.all())
    
    def total_formateado(self):
        total_precio = self.total()
        partes = f"{total_precio:.2f}".split(".")
        parte_entera = intcomma(int(partes[0]))
        return f"{parte_entera},{partes[1]}"

class Testimonio(models.Model):
    nombre = models.CharField(max_length=100)
    mensaje = models.TextField()
    imagen = models.ImageField(upload_to='testimonios/', blank=True, null=True)
    
    def __str__(self):
        return f"{self.nombre}"