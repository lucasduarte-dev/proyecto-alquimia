from django.contrib import admin
from .models import *
# Register your models here.

admin.site.register(Producto)
admin.site.register(CategoriaProducto)
admin.site.register(Curso)
admin.site.register(Testimonio)
admin.site.register(UserProfile)