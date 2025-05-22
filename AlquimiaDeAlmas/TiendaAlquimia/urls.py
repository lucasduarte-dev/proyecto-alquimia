from django.urls import path
from . import views
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth.views import LogoutView
from django.contrib.auth import views as auth_views
from TiendaAlquimia.forms import CustomPasswordResetForm, CustomSetPasswordForm


urlpatterns=[
    path('', views.inicio, name='inicio'),
    path('login/',views.login_request,name='login'),
    path('register/',views.register,name='register'),
    path('logout/', LogoutView.as_view(next_page='inicio'), name='logout'),
    path('activar-cuenta/<uidb64>/<token>/', views.activar_cuenta, name='activar_cuenta'),
    path('recuperar-contraseña/', 
         auth_views.PasswordResetView.as_view(
             form_class=CustomPasswordResetForm,
             template_name='TiendaAlquimia/password_reset_form.html',
             email_template_name='TiendaAlquimia/email/password_reset_email.html',
             html_email_template_name='TiendaAlquimia/email/password_reset_email.html',
             subject_template_name='TiendaAlquimia/email/password_reset_subject.txt'
         ), 
         name='password_reset'),

    # Mensaje enviado
    path('recuperar-contraseña/enviado/', 
         auth_views.PasswordResetDoneView.as_view(template_name='TiendaAlquimia/password_reset_done.html'), 
         name='password_reset_done'),

    # Link con token
    path('recuperar-contraseña/<uidb64>/<token>/',
         auth_views.PasswordResetConfirmView.as_view(
             form_class=CustomSetPasswordForm,
             template_name='TiendaAlquimia/password_reset_confirm.html'
         ), 
         name='password_reset_confirm'),

    # Contraseña cambiada correctamente
    path('recuperar-contraseña/completo/', 
         auth_views.PasswordResetCompleteView.as_view(template_name='TiendaAlquimia/password_reset_complete.html'), 
         name='password_reset_complete'),
    path('cursos/', views.cursos, name='cursos'),
    path('productos/', views.productos, name='productos'),
    path('producto/<int:producto_id>/', views.detalle_producto, name='detalle_producto'),
    path('proceder-pago/', views.proceder_pago, name='proceder_pago'),
    path('verificar-pago/<str:payment_id>/', views.verificar_pago, name='verificar_pago'),
    path('webhooks/mercadopago/', views.mercadopago_webhook, name='mercadopago_webhook'),
    path('compra-exitosa/', views.compra_exitosa, name='compra_exitosa'),
    path('sobre_nosotras/', views.sobre_nosotras, name='sobre_nosotras'),
    path('carrito/', views.carrito, name='carrito'),
    path('agregar-al-carrito/<int:producto_id>/', views.agregar_al_carrito, name='agregar_al_carrito'),
    path('proceder-pago/', views.proceder_pago, name='proceder_pago'),
    path('sumar-item/<int:producto_id>/', views.sumar_item, name='sumar_item'),
    path('agregar-al-carrito-redirect/<int:producto_id>/', views.agregar_al_carrito_redirect, name='agregar_al_carrito_redirect'),
    path('carrito/restar/<int:producto_id>/', views.restar_del_carrito, name='restar_del_carrito'),
    path('carrito/eliminar/<int:producto_id>/', views.eliminar_del_carrito, name='eliminar_del_carrito'),
    path('lista_jabones/', views.lista_jabones, name='Jabones'),
    path('productos/spray/', views.lista_spray_auricos, name='productos_spray'),
    path('productos/oraculo/', views.lista_oraculos, name='productos_oraculos'),
    path('productos/lista_meditaciones/', views.lista_meditaciones, name='lista_meditaciones'),

 
 ]

if settings.DEBUG:  # Solo en modo DEBUG
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)