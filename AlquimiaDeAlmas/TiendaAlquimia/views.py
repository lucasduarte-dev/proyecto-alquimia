from django.shortcuts import render, redirect, get_object_or_404
from TiendaAlquimia.forms import UserCreationFormCustom, AuthenticationFormCustom
from django.contrib.auth import login, authenticate
from .models import Curso, Producto, CategoriaProducto, Testimonio, User, UserProfile
from django.contrib.humanize.templatetags.humanize import intcomma
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.contrib import messages
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from datetime import datetime
import mercadopago
from django.urls import reverse
from django.http import HttpResponse, JsonResponse
import json
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from .micorreo_api import MiCorreoAPI
import logging

# Configurar logging
logger = logging.getLogger(__name__)

def format_price(price):
    """Formatea un precio a formato ARS (ej: 1234.56 -> 1.234,56)"""
    return f"{float(price):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# VISTAS DE LAS PÁGINAS
def inicio(request):
    testimonios = Testimonio.objects.all()
    return render(request, 'TiendaAlquimia/base.html', {'testimonios': testimonios})

@login_required
def productos(request):
    productos = Producto.objects.all()
    return render(request, 'TiendaAlquimia/productos.html', {'productos': productos})

@login_required
def cursos(request):
    cursos = Curso.objects.all()
    return render(request, 'TiendaAlquimia/cursos.html', {'cursos': cursos})

def sobre_nosotras(request):
    return render(request, 'TiendaAlquimia/sobre_nosotras.html')

@login_required
def carrito(request):
    carrito = request.session.get('carrito', {})
    total = 0

    for producto_id, item in carrito.items():
        try:
            producto = Producto.objects.get(id=producto_id)
            item['descripcion'] = producto.descripcion
        except Producto.DoesNotExist:
            item['descripcion'] = 'Descripción no disponible'

        item['subtotal'] = item['precio'] * item['cantidad']
        total += item['subtotal']

        item['precio_formateado'] = format_price(item['precio'])
        item['subtotal_formateado'] = format_price(item['subtotal'])

    total_formateado = format_price(total) if total > 0 else "0,00"

    return render(request, 'TiendaAlquimia/carrito.html', {
        'carrito': carrito,
        'total': total,
        'total_formateado': total_formateado
    })

def compra_exitosa(request):
    carrito = request.session.get('carrito', {})
    
    if not carrito:
        messages.warning(request, "No hay productos en el carrito para finalizar la compra.")
        return redirect('productos')
    
    total = 0
    for producto_id, item in carrito.items():
        if 'precio' in item and 'cantidad' in item:
            item['subtotal'] = item['precio'] * item['cantidad']
            total += item['subtotal']
            
            item['precio_formateado'] = format_price(item['precio'])
            item['subtotal_formateado'] = format_price(item['subtotal'])
            
            try:
                producto = Producto.objects.get(id=producto_id)
                if producto.stock >= item['cantidad']:
                    producto.stock -= item['cantidad']
                    producto.save()
                else:
                    messages.error(request, f"No hay suficiente stock de {producto.nombre}. Disponible: {producto.stock}")
                    return redirect('carrito')
            except Producto.DoesNotExist:
                messages.error(request, f"Producto con ID {producto_id} no encontrado")
                return redirect('carrito')
    
    total_formateado = format_price(total) if total > 0 else "0,00"
    
    order_id = None
    shipping_address = None
    delivery_type = None
    tracking_number = None
    shipping_status = "Creado"
    
    if request.user.is_authenticated:
        try:
            micorreo_api = MiCorreoAPI()
            customer_id = request.user.profile.micorreo_customer_id
            if not customer_id:
                messages.warning(request, "Usuario no registrado en MiCorreo. Contacta al soporte.")
            else:
                total_weight = sum(Producto.objects.get(id=pid).peso_gramos * item['cantidad'] for pid, item in carrito.items())
                max_height = max(Producto.objects.get(id=pid).alto_cm for pid in carrito.keys())
                max_width = max(Producto.objects.get(id=pid).ancho_cm for pid in carrito.keys())
                max_length = max(Producto.objects.get(id=pid).largo_cm for pid in carrito.keys())
                
                profile = request.user.profile
                order_id = f"ALQ-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                shipping_address = f"{profile.street_name or 'Default Street'} {profile.street_number or '123'}, {profile.city or 'Buenos Aires'}, {profile.postal_code or 'C1425AAE'}"
                delivery_type = "Entrega a domicilio"
                
                shipping_data = {
                    "customerId": customer_id,
                    "extOrderId": order_id,
                    "orderNumber": order_id,
                    "sender": {
                        "name": "Alquimia de Almas",
                        "phone": "5491141846727",
                        "email": settings.EMAIL_HOST_USER,
                        "originAddress": {
                            "streetName": "Vicente Lopez",
                            "streetNumber": "448",
                            "city": "Monte Grande",
                            "provinceCode": "B",
                            "postalCode": "B1842ZAB"
                        }
                    },
                    "recipient": {
                        "name": request.user.get_full_name() or request.user.username,
                        "email": request.user.email,
                        "phone": profile.phone or "5491141846727",
                    },
                    "shipping": {
                        "deliveryType": "D",
                        "address": {
                            "streetName": profile.street_name or "Default Street",
                            "streetNumber": profile.street_number or "123",
                            "city": profile.city or "Buenos Aires",
                            "provinceCode": profile.province_code or "C",
                            "postalCode": profile.postal_code or "C1425AAE"
                        },
                        "weight": total_weight,
                        "declaredValue": float(total),
                        "height": max_height,
                        "length": max_length,
                        "width": max_width
                    }
                }
                
                response = micorreo_api.import_shipping(shipping_data)
                if response.status_code != 200:
                    error = response.json().get('message', 'Error desconocido')
                    messages.error(request, f"Error al importar envío: {error}")
                    shipping_status = "Error"
                else:
                    messages.success(request, "Envío importado correctamente a MiCorreo")
                    # Opcional: Consultar estado del envío
                    try:
                        status_response = micorreo_api.get_shipping_status(order_id)
                        if status_response.status_code == 200:
                            shipping_status = status_response.json().get('status', 'Creado')
                            tracking_number = status_response.json().get('tracking_number', None)
                            logger.info(f"Estado del envío {order_id}: {shipping_status}")
                        else:
                            logger.warning(f"No se pudo verificar estado del envío {order_id}: {status_response.text}")
                    except AttributeError:
                        logger.info("Método get_shipping_status no implementado")
                    except Exception as e:
                        logger.error(f"Error al verificar estado del envío: {str(e)}")
                
        except Exception as e:
            logger.error(f"Error al procesar envío en compra_exitosa: {str(e)}")
            messages.error(request, f"Error al procesar envío: {str(e)}")
            shipping_status = "Error"
    
    if request.user.is_authenticated:
        try:
            enviar_mail_compra(
                usuario=request.user,
                carrito=carrito,
                total_formateado=total_formateado,
                order_id=order_id or "No disponible",
                shipping_address=shipping_address or "No disponible",
                delivery_type=delivery_type or "No disponible",
                tracking_number=tracking_number,
                shipping_status=shipping_status
            )
        except Exception as e:
            logger.error(f"Error al enviar correo de confirmación: {str(e)}")
            messages.error(request, f"Error al enviar correo de confirmación: {str(e)}")
    
    carrito_copia = carrito.copy()
    request.session['carrito'] = {}
    request.session.modified = True
    
    return render(request, 'TiendaAlquimia/compra_exitosa.html', {
        'carrito': carrito_copia,
        'total_formateado': total_formateado
    })

# VISTAS DE CATEGORÍAS
@login_required
def lista_jabones(request):
    categoria_jabones = CategoriaProducto.objects.get(nombre='Jabones')
    productos = Producto.objects.filter(categoria=categoria_jabones)
    return render(request, 'TiendaAlquimia/lista_jabones.html', {'productos': productos})

@login_required
def lista_spray_auricos(request):
    categoria_spray_auricos = CategoriaProducto.objects.get(nombre='spray_auricos')
    productos = Producto.objects.filter(categoria=categoria_spray_auricos)
    return render(request, 'TiendaAlquimia/lista_sprays_auricos.html', {'productos': productos})

@login_required
def lista_oraculos(request):
    categoria_oraculos = CategoriaProducto.objects.get(nombre='Oraculos')
    productos = Producto.objects.filter(categoria=categoria_oraculos)
    return render(request, 'TiendaAlquimia/lista_Oraculos.html', {'productos': productos})

@login_required
def lista_meditaciones(request):
    categoria_meditaciones = CategoriaProducto.objects.get(nombre='Meditaciones')
    productos = Producto.objects.filter(categoria=categoria_meditaciones)
    return render(request, 'TiendaAlquimia/lista_meditaciones.html', {'productos': productos})

# DETALLE PRODUCTO
def detalle_producto(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)
    productos_relacionados = Producto.objects.filter(categoria=producto.categoria).exclude(id=producto_id).distinct()[:10]
    carrito = request.session.get('carrito', {})
    cantidad = carrito.get(str(producto_id), {}).get('cantidad', 0)

    return render(request, 'TiendaAlquimia/detalle_producto.html', {
        'producto': producto,
        'productos_relacionados': productos_relacionados,
        'producto_id': producto_id,
        'cantidad': cantidad,
    })

# AUTENTICACIÓN
def login_request(request):
    if request.method == 'POST':
        form = AuthenticationFormCustom(request, data=request.POST)
        if form.is_valid():
            usuario = form.cleaned_data.get('username')
            contraseña = form.cleaned_data.get('password')
            user = authenticate(username=usuario, password=contraseña)
            login(request, user)
            return redirect('inicio')
    else:
        form = AuthenticationFormCustom()
    return render(request, 'TiendaAlquimia/login.html', {"form": form})

def register(request):
    if request.method == 'POST':
        form = UserCreationFormCustom(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()
            
            UserProfile.objects.create(user=user)
            
            micorreo_api = MiCorreoAPI()
            micorreo_data = {
                "firstName": user.first_name or user.username,
                "lastName": user.last_name or "",
                "email": user.email,
                "password": form.cleaned_data['password1'],
                "documentType": "DNI",
                "documentId": "12345678",
                "phone": "5491141846727",
                "address": {
                    "streetName": "Default Street",
                    "streetNumber": "123",
                    "city": "Buenos Aires",
                    "provinceCode": "C",
                    "postalCode": "C1425AAE"
                }
            }
            
            try:
                existing_customer_id = micorreo_api.get_customer_by_email(
                    email=user.email,
                    password=form.cleaned_data['password1']
                )
                
                if existing_customer_id:
                    user.profile.micorreo_customer_id = existing_customer_id
                    user.profile.save()
                    logger.info(f"Usuario {user.username} ya existía en MiCorreo con ID: {existing_customer_id}")
                    messages.info(request, "Ya estabas registrado en el servicio de envíos. Datos actualizados correctamente.")
                else:
                    response = micorreo_api.register_user(micorreo_data)
                    
                    if response.status_code == 200:
                        response_data = response.json()
                        if 'customerId' in response_data:
                            user.profile.micorreo_customer_id = response_data['customerId']
                            user.profile.save()
                            logger.info(f"Usuario {user.username} registrado en MiCorreo con ID: {user.profile.micorreo_customer_id}")
                        else:
                            logger.warning(f"Respuesta sin customerId: {response_data}")
                    else:
                        try:
                            error_data = response.json()
                            error_msg = error_data.get('message', 'Error desconocido')
                            if 'ya fue dado de alta exitosamente' in error_msg:
                                customer_id = micorreo_api.get_customer_by_email(
                                    email=user.email,
                                    password=form.cleaned_data['password1']
                                )
                                if customer_id:
                                    user.profile.micorreo_customer_id = customer_id
                                    user.profile.save()
                                    logger.info(f"Usuario {user.username} ya existía en MiCorreo. ID recuperado: {customer_id}")
                            else:
                                logger.error(f"Error al registrar usuario {user.username} en MiCorreo: {error_msg}")
                                messages.warning(request, f"Error al registrar en MiCorreo: {error_msg}")
                        except Exception:
                            logger.error(f"Error al procesar respuesta: {response.text}")
            except Exception as e:
                logger.error(f"Excepción al registrar usuario {user.username} en MiCorreo: {str(e)}")
                messages.warning(request, f"Error al conectar con MiCorreo: {str(e)}")
            
            enviar_confirmacion_email(request, user)
            messages.success(request, 'Te registraste correctamente. Revisá tu correo para activar tu cuenta.')
            return redirect('login')
    else:
        form = UserCreationFormCustom()
    return render(request, 'TiendaAlquimia/register.html', {"form": form})

# MANEJO DE EMAILS
def enviar_confirmacion_email(request, user):
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    url_activacion = request.build_absolute_uri(
        reverse('activar_cuenta', kwargs={'uidb64': uid, 'token': token})
    )
    contexto = {
        'usuario': user,
        'url_activacion': url_activacion
    }
    asunto = 'Confirmá tu cuenta en Alquimia'
    from_email = settings.EMAIL_HOST_USER
    to = [user.email]
    html_content = render_to_string('TiendaAlquimia/email/confirmacion_email.html', contexto)
    text_content = f'Hola {user.username}, hacé clic en este link para activar tu cuenta: {url_activacion}'
    email = EmailMultiAlternatives(asunto, text_content, from_email, to)
    email.attach_alternative(html_content, "text/html")
    email.send()

def activar_cuenta(request, uidb64, token):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        messages.success(request, 'Tu cuenta fue activada con éxito. Ya podés iniciar sesión.')
        return redirect('login')
    else:
        messages.error(request, 'El enlace de activación es inválido o ha expirado.')
        return redirect('inicio')

# CARRITO
@login_required
def agregar_al_carrito(request, producto_id):
    if request.method == 'POST':
        producto = get_object_or_404(Producto, id=producto_id)
        carrito = request.session.get('carrito', {})
        if str(producto_id) in carrito:
            carrito[str(producto_id)]['cantidad'] += 1
        else:
            carrito[str(producto_id)] = {
                'imagen': producto.imagen.url if producto.imagen else '',
                'nombre': producto.nombre,
                'precio': float(producto.precio),
                'cantidad': 1,
            }
        request.session['carrito'] = carrito
    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def sumar_item(request, producto_id):
    if request.method == 'POST':
        producto = get_object_or_404(Producto, id=producto_id)
        carrito = request.session.get('carrito', {})
        if str(producto_id) in carrito:
            carrito[str(producto_id)]['cantidad'] += 1
        else:
            carrito[str(producto_id)] = {
                'imagen': producto.imagen.url if producto.imagen else '',
                'nombre': producto.nombre,
                'precio': float(producto.precio),
                'cantidad': 1,
            }
        request.session['carrito'] = carrito
    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def agregar_al_carrito_redirect(request, producto_id):
    if request.method == 'POST':
        producto = get_object_or_404(Producto, id=producto_id)
        carrito = request.session.get('carrito', {})
        if str(producto_id) not in carrito:
            carrito[str(producto_id)] = {
                'imagen': producto.imagen.url if producto.imagen else '',
                'nombre': producto.nombre,
                'precio': float(producto.precio),
                'cantidad': 1,
            }
        request.session['carrito'] = carrito
    return redirect('carrito')

@login_required
def restar_del_carrito(request, producto_id):
    carrito = request.session.get('carrito', {})
    if str(producto_id) in carrito:
        if carrito[str(producto_id)]['cantidad'] > 1:
            carrito[str(producto_id)]['cantidad'] -= 1
        else:
            del carrito[str(producto_id)]
    request.session['carrito'] = carrito
    return redirect(request.META.get('HTTP_REFERER', '/'))

@login_required
def eliminar_del_carrito(request, producto_id):
    carrito = request.session.get('carrito', {})
    if str(producto_id) in carrito:
        del carrito[str(producto_id)]
    request.session['carrito'] = carrito
    return redirect('carrito')

# EMAILS
def enviar_mail_compra(usuario, carrito, total_formateado, order_id, shipping_address, delivery_type, tracking_number=None, shipping_status="Creado"):
    asunto = '¡Gracias por tu compra en Alquimia!'
    from_email = settings.EMAIL_HOST_USER
    to = [usuario.email]
    numero_whatsapp = "5491141846727"
    mensaje = "Hola! Quiero coordinar el envío de mi compra en Alquimia."
    mensaje_encoded = mensaje.replace(" ", "%20")
    link_whatsapp = f"https://wa.me/{numero_whatsapp}?text={mensaje_encoded}"
    contexto = {
        'user': usuario,
        'carrito': carrito.values(),
        'total_formateado': total_formateado,
        'current_year': datetime.now().year,
        'link_whatsapp': link_whatsapp,
        'order_id': order_id,
        'shipping_address': shipping_address,
        'delivery_type': delivery_type,
        'tracking_number': tracking_number,
        'shipping_status': shipping_status,
    }
    html_content = render_to_string('TiendaAlquimia/email/compra_confirmada.html', contexto)
    text_content = f"Gracias por tu compra, {usuario.first_name}. Número de pedido: {order_id}"
    email = EmailMultiAlternatives(asunto, text_content, from_email, to)
    email.attach_alternative(html_content, "text/html")
    email.send()

def enviar_email_restablecer_contraseña(usuario, request):
    asunto = 'Restablecimiento de Contraseña'
    from_email = settings.EMAIL_HOST_USER
    to = [usuario.email]
    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    token = default_token_generator.make_token(usuario)
    contexto = {
        'user': usuario,
        'uid': uid,
        'token': token,
        'protocol': 'https' if request.is_secure() else 'http',
        'domain': request.get_host(),
        'site_name': 'Alquimia de Almas',
    }
    html_content = render_to_string('TiendaAlquimia/email/password_reset_email.html', contexto)
    text_content = f"Hola {usuario.username},\n\nRecibimos una solicitud para restablecer tu contraseña."
    email = EmailMultiAlternatives(asunto, text_content, from_email, to)
    email.attach_alternative(html_content, "text/html")
    email.send()

# MERCADO PAGO
@csrf_exempt
@require_POST
def mercadopago_webhook(request):
    try:
        body_unicode = request.body.decode('utf-8')
        data = json.loads(body_unicode)
        logger.info(f"Webhook recibido: {data}")
        return HttpResponse("Webhook procesado correctamente", status=200)
    except json.JSONDecodeError:
        logger.error("Error decodificando JSON del webhook")
        return HttpResponse("Bad Request: JSON inválido", status=400)
    except Exception as e:
        logger.error(f"Error inesperado en webhook: {str(e)}")
        return HttpResponse("Error interno del servidor", status=500)

# GUARDAR CÓDIGO POSTAL
@login_required
@require_POST
def guardar_codigo_postal(request):
    try:
        data = json.loads(request.body)
        postal_code = data.get('postalCode')
        if not postal_code:
            return JsonResponse({'error': 'Código postal requerido'}, status=400)
        
        request.session['shipping_postal_code'] = postal_code
        profile = request.user.profile
        profile.postal_code = postal_code
        profile.save()
        
        return JsonResponse({'success': 'Código postal guardado correctamente'}, status=200)
    except json.JSONDecodeError:
        logger.error("Error decodificando JSON en guardar_codigo_postal")
        return JsonResponse({'error': 'JSON inválido'}, status=400)
    except Exception as e:
        logger.error(f"Error en guardar_codigo_postal: {str(e)}")
        return JsonResponse({'error': 'Error interno del servidor'}, status=500)

# PAGOS
@login_required
def proceder_pago(request):
    """
    Vista para procesar el pago y la información de envío.
    Integra MercadoPago y la API de MiCorreo para ofrecer opciones de envío.
    """
    carrito = request.session.get('carrito', {})
    products_total = 0  # Total de los productos (sin envío)
    shipping_rates = None
    show_address_form = True
    shipping_error = None
    shipping_info = {}
    selected_shipping_rate = None
    selected_shipping_cost = 0  # Costo de envío seleccionado

    # Verificar si hay productos en el carrito
    if not carrito:
        messages.warning(request, "No hay productos en el carrito.")
        return redirect('productos')

    # Validar productos y calcular total de productos
    productos_validos = []
    for producto_id, item in carrito.items():
        try:
            producto = Producto.objects.get(id=producto_id)
            item['descripcion'] = producto.descripcion
            productos_validos.append(producto)
            
            # Verificar stock
            if producto.stock < item['cantidad']:
                messages.error(request, f"No hay suficiente stock de {producto.nombre}. Disponible: {producto.stock}")
                return redirect('carrito')
                
            # Calcular subtotales
            item['subtotal'] = float(item['precio']) * item['cantidad']
            products_total += item['subtotal']
            
            # Formatear precios para mostrar
            item['precio_formateado'] = format_price(item['precio'])
            item['subtotal_formateado'] = format_price(item['subtotal'])
            
        except Producto.DoesNotExist:
            # Eliminar productos que ya no existen
            del carrito[str(producto_id)]
            request.session['carrito'] = carrito
            messages.error(request, f"Un producto en tu carrito ya no existe.")
            return redirect('carrito')

    # Formatear total de productos para mostrar
    products_total_formateado = format_price(products_total) if products_total > 0 else "0,00"
    
    # Depurar el carrito y el total
    logger.info(f"Carrito: {carrito}")
    logger.info(f"Total de productos (sin envío): {products_total}")

    # PASO 1: Manejar formulario de dirección
    if request.method == 'POST' and 'streetName' in request.POST:
        try:
            # Asegurar que el usuario tiene perfil
            profile, created = UserProfile.objects.get_or_create(user=request.user)
            
            # Actualizar datos de dirección
            profile.street_name = request.POST['streetName'].strip()
            profile.street_number = request.POST['streetNumber'].strip()
            profile.city = request.POST['city'].strip()
            profile.province_code = request.POST['provinceCode'].strip()
            profile.postal_code = request.POST['postalCode'].strip()
            profile.phone = request.POST.get('phone', '').strip() or profile.phone or "5491141846727"
            profile.save()
            
            # Guardar código postal en sesión para cotizaciones
            request.session['shipping_postal_code'] = request.POST['postalCode'].strip()
            
            messages.success(request, "Dirección actualizada correctamente.")
            return redirect('proceder_pago')
        except Exception as e:
            logger.error(f"Error al guardar dirección: {str(e)}")
            messages.error(request, "Error al guardar la dirección. Por favor, intenta nuevamente.")
            return redirect('proceder_pago')

    # PASO 2: Manejar actualización de preferencia de MercadoPago por AJAX
    if request.method == 'POST' and request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
            new_total = data.get('total')
            shipping_option_id = data.get('shipping_option_id')
            
            logger.info(f"Solicitud AJAX recibida: total={new_total}, shipping_option_id={shipping_option_id}")
            
            # Validar new_total
            try:
                new_total = float(new_total)
                if new_total <= 0:
                    logger.error("Total inválido: debe ser mayor que cero")
                    return JsonResponse({'error': 'Total inválido o no proporcionado'}, status=400)
            except (TypeError, ValueError):
                logger.error(f"Total inválido: {new_total}")
                return JsonResponse({'error': 'Total debe ser un número válido'}, status=400)
            
            # Crear preferencia de MercadoPago
            sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)
            preference_data = {
                "items": [
                    {
                        "title": "Compra en Alquimia",
                        "quantity": 1,
                        "unit_price": new_total,
                        "currency_id": "ARS",
                        "description": f"Compra en Alquimia - {len(carrito)} productos"
                    }
                ],
                "back_urls": {
                    "success": "https://bde3-190-192-199-42.ngrok-free.app/compra-exitosa/",
                    "failure": "https://bde3-190-192-199-42.ngrok-free.app/carrito/",
                    "pending": "https://bde3-190-192-199-42.ngrok-free.app/carrito/"
                },
                "auto_return": "approved",
                "notification_url": "https://bde3-190-192-199-42.ngrok-free.app/webhooks/mercadopago/"
            }
            # Agregar external_reference solo si shipping_option_id está presente y válido
            if shipping_option_id and shipping_option_id != "D_None":
                preference_data["external_reference"] = f"SHIPPING_{shipping_option_id}"
                request.session['selected_shipping_option'] = shipping_option_id
            
            logger.info(f"Datos de preferencia: {preference_data}")
            
            preference_response = sdk.preference().create(preference_data)
            if preference_response.get("response") and preference_response["response"].get("id"):
                preference = preference_response["response"]
                logger.info(f"Preferencia creada: {preference}")
                
                return JsonResponse({
                    'preference_id': preference.get('id'),
                    'init_point': preference.get('init_point')
                })
            else:
                logger.error(f"Error en la respuesta de MercadoPago: {preference_response}")
                return JsonResponse({'error': 'No se pudo crear la preferencia de pago'}, status=500)
                
        except json.JSONDecodeError as e:
            logger.error(f"Error decodificando JSON en actualización de preferencia: {str(e)}")
            return JsonResponse({'error': 'Formato de datos inválido'}, status=400)
        except mercadopago.exceptions.MPError as e:
            logger.error(f"Error de MercadoPago al crear preferencia: {str(e)}")
            return JsonResponse({'error': f'Error de MercadoPago: {str(e)}'}, status=500)
        except Exception as e:
            logger.error(f"Error inesperado al actualizar preferencia de MercadoPago: {str(e)}")
            return JsonResponse({'error': 'Error interno del servidor'}, status=500)

    # PASO 3: Integración con MiCorreo para opciones de envío
    if request.user.is_authenticated and productos_validos:
        try:
            # Asegurar que el usuario tiene perfil
            profile, created = UserProfile.objects.get_or_create(user=request.user)
            
            # Inicializar API de MiCorreo
            micorreo_api = MiCorreoAPI()
            micorreo_api.set_cart_total(products_total)  # Establecer total para validaciones
            
            # Verificar si el usuario tiene customerId o necesita ser registrado
            customer_id = profile.micorreo_customer_id
            if not customer_id:
                logger.info(f"Usuario {request.user.username} no tiene customerId. Intentando recuperar/registrar...")
                
                # Intentar recuperar ID existente
                try:
                    existing_customer_id = micorreo_api.get_customer_by_email(request.user.email)
                    if existing_customer_id:
                        logger.info(f"Se encontró un customer_id existente: {existing_customer_id}")
                        customer_id = existing_customer_id
                        profile.micorreo_customer_id = customer_id
                        profile.save()
                    else:
                        # Registrar usuario en MiCorreo
                        logger.info("No se encontró customer_id. Registrando usuario...")
                        user_data = {
                            "firstName": request.user.first_name or request.user.username,
                            "lastName": request.user.last_name or "Consumidor",
                            "email": request.user.email,
                            "password": "TemporaryPassword123",  # Considerar generar contraseña aleatoria
                            "documentType": "DNI",
                            "documentId": profile.document_id or "47390233",
                            "phone": profile.phone or "5491141846727",
                            "address": {
                                "streetName": profile.street_name or "Av. Rivadavia",
                                "streetNumber": profile.street_number or "1200",
                                "city": profile.city or "Buenos Aires",
                                "provinceCode": profile.province_code or "C",
                                "postalCode": profile.postal_code or "C1425AAE"
                            }
                        }
                        
                        response = micorreo_api.register_user(user_data)
                        if response.status_code in [200, 202]:
                            data = response.json()
                            customer_id = data.get('customerId')
                            if customer_id:
                                logger.info(f"Usuario registrado exitosamente con ID: {customer_id}")
                                profile.micorreo_customer_id = customer_id
                                profile.save()
                            else:
                                logger.warning(f"Respuesta sin customerId: {data}")
                                shipping_error = "Error al registrar en el servicio de envíos: falta ID de cliente"
                        else:
                            error_msg = response.json().get('message', 'Desconocido')
                            logger.error(f"Error al registrar usuario: {error_msg}")
                            shipping_error = f"Error al registrar en el servicio de envíos: {error_msg}"
                except Exception as reg_error:
                    logger.error(f"Excepción al registrar usuario: {str(reg_error)}")
                    shipping_error = f"Error de conexión con el servicio de envíos: {str(reg_error)}"
            
            # Si tenemos customer_id, proceder a cotizar envío
            if customer_id and not shipping_error:
                # Calcular dimensiones del paquete
                total_weight = max(1000, sum(p.peso_gramos * carrito[str(p.id)]['cantidad'] for p in productos_validos))
                max_height = max(10, max(p.alto_cm for p in productos_validos))
                max_width = max(10, max(p.ancho_cm for p in productos_validos))
                max_length = max(10, max(p.largo_cm for p in productos_validos))
                
                # Obtener código postal del destinatario
                postal_code = request.session.get('shipping_postal_code') or profile.postal_code or "C1425AAE"
                
                # Preparar datos para cotización
                rate_data = {
                    "customerId": customer_id,
                    "postalCodeOrigin": "B1842ZAB",  # Código postal de origen (Alquimia)
                    "postalCodeDestination": postal_code,
                    "dimensions": {
                        "weight": total_weight,
                        "height": max_height,
                        "width": max_width,
                        "length": max_length
                    }
                }
                
                # Guardar información de envío para la vista
                shipping_info = {
                    "dimensions": {
                        "weight": f"{total_weight/1000:.1f}kg",
                        "height": f"{max_height}cm",
                        "width": f"{max_width}cm",
                        "length": f"{max_length}cm"
                    },
                    "origin": "Monte Grande (B1842ZAB)",
                    "destination": postal_code
                }
                
                # Solicitar cotización a MiCorreo
                logger.info(f"Solicitando cotización con datos: {json.dumps(rate_data, indent=2)}")
                try:
                    response = micorreo_api.get_shipping_rates(rate_data)
                    
                    if response.status_code in [200, 202]:
                        data = response.json()
                        if 'rates' in data and data['rates']:
                            shipping_rates = data['rates']
                            
                            # Formatear y ordenar tarifas
                            for rate in shipping_rates:
                                rate['price_formateado'] = format_price(float(rate['price']))
                                # Validar que productId exista para evitar unique_id inválido
                                product_id = rate.get('productId', 'UNKNOWN')
                                rate['unique_id'] = f"{rate.get('deliveredType')}_{product_id}"
                                
                                # Mejorar la presentación de tiempos de entrega
                                min_time = rate.get('deliveryTimeMin', '2')
                                max_time = rate.get('deliveryTimeMax', '5')
                                if min_time == max_time:
                                    rate['delivery_time_display'] = f"{min_time} días hábiles"
                                else:
                                    rate['delivery_time_display'] = f"{min_time} a {max_time} días hábiles"
                                
                                # Mejorar la presentación del tipo de entrega
                                if rate.get('deliveredType') == 'D':
                                    rate['delivery_type_display'] = "Entrega a domicilio"
                                else:
                                    rate['delivery_type_display'] = "Retiro en sucursal"
                            
                            # Ordenar por precio (más barato primero)
                            shipping_rates.sort(key=lambda x: float(x.get('price', 0)))
                            
                            # Separar opciones por tipo de entrega
                            home_delivery_rates = [r for r in shipping_rates if r.get('deliveredType') == 'D']
                            branch_delivery_rates = [r for r in shipping_rates if r.get('deliveredType') == 'S']
                            
                            # Verificar si se requiere mostrar el formulario de dirección
                            show_address_form = bool(home_delivery_rates)
                            
                            # Seleccionar opción de envío predeterminada (más barata a domicilio)
                            if home_delivery_rates:
                                selected_rate = min(home_delivery_rates, key=lambda x: float(x.get('price', 0)))
                                selected_shipping_cost = float(selected_rate['price'])
                                selected_shipping_rate = selected_rate
                                logger.info(f"Tarifa seleccionada: {selected_rate['productName']} - ${selected_shipping_cost}")
                            elif branch_delivery_rates:
                                # Si no hay entrega a domicilio, seleccionar la más barata a sucursal
                                selected_rate = min(branch_delivery_rates, key=lambda x: float(x.get('price', 0)))
                                selected_shipping_cost = float(selected_rate['price'])
                                selected_shipping_rate = selected_rate
                                logger.info(f"Tarifa a sucursal seleccionada: {selected_rate['productName']} - ${selected_shipping_cost}")
                                
                                # Advertir al usuario que no hay opciones a domicilio
                                messages.info(request, "No se encontraron opciones de entrega a domicilio para tu código postal. Solo mostramos opciones de retiro en sucursal.")
                            else:
                                shipping_error = "No se encontraron opciones de envío válidas."
                        else:
                            shipping_error = "No se encontraron tarifas de envío disponibles para tu código postal."
                    else:
                        try:
                            error_data = response.json()
                            error_msg = error_data.get('message', 'Desconocido')
                            shipping_error = f"Error al obtener cotización: {error_msg}"
                        except:
                            shipping_error = f"Error al obtener cotización. Código: {response.status_code}"
                except Exception as e:
                    logger.error(f"Excepción al solicitar tarifas: {str(e)}")
                    shipping_error = f"Error al conectar con el servicio de envíos: {str(e)}"
        except Exception as e:
            logger.error(f"Error general al procesar envío: {str(e)}")
            shipping_error = "Error al procesar información de envío. Por favor, intenta nuevamente."
    
    # Mostrar errores de envío si existen
    if shipping_error:
        messages.error(request, shipping_error)
    
    # PASO 4: Crear preferencia de MercadoPago inicial
    preference = {"id": None, "init_point": None}
    try:
        sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)
        preference_data = {
            "items": [
                {
                    "title": "Compra en Alquimia",
                    "quantity": 1,
                    "unit_price": float(products_total + selected_shipping_cost),  # Total con envío
                    "currency_id": "ARS",
                    "description": f"Compra en Alquimia - {len(carrito)} productos"
                }
            ],
            "back_urls": {
                "success": "https://bde3-190-192-199-42.ngrok-free.app/compra-exitosa/",
                "failure": "https://bde3-190-192-199-42.ngrok-free.app/carrito/",
                "pending": "https://bde3-190-192-199-42.ngrok-free.app/carrito/"
            },
            "auto_return": "approved",
            "notification_url": "https://bde3-190-192-199-42.ngrok-free.app/webhooks/mercadopago/"
        }
        
        # Si hay una opción de envío seleccionada, guardarla como referencia externa
        if selected_shipping_rate and selected_shipping_rate.get('unique_id') != "D_None":
            preference_data["external_reference"] = f"SHIPPING_{selected_shipping_rate.get('unique_id')}"
        
        logger.info(f"Creando preferencia inicial con datos: {preference_data}")
        
        preference_response = sdk.preference().create(preference_data)
        if preference_response.get("response") and preference_response["response"].get("id"):
            preference = preference_response["response"]
            logger.info(f"Preferencia inicial creada: {preference}")
            
            # Guardar la preferencia en sesión para referencia
            request.session['mercado_pago_preference'] = {
                'id': preference.get('id'),
                'total': float(products_total + selected_shipping_cost)
            }
        else:
            logger.error(f"Error en la respuesta de MercadoPago: {preference_response}")
            messages.error(request, "No se pudo crear la preferencia de pago inicial.")
    except mercadopago.exceptions.MPError as e:
        logger.error(f"Error de MercadoPago al crear preferencia inicial: {str(e)}")
        messages.error(request, "Error al configurar el pago con MercadoPago. Por favor, intenta más tarde.")
    except Exception as e:
        logger.error(f"Error inesperado al crear preferencia inicial de MercadoPago: {str(e)}")
        messages.error(request, "Error interno al configurar el pago. Por favor, intenta más tarde.")

    # Renderizar template con todos los datos
    return render(request, 'TiendaAlquimia/proceder_pago.html', {
        'carrito': carrito,
        'total': products_total,  # Total de productos (sin envío)
        'total_formateado': products_total_formateado,  # Formateado: "13.234,00"
        'preference_id': preference.get('id'),
        'public_key': settings.MERCADO_PAGO_PUBLIC_KEY,
        'init_point': preference.get('init_point'),
        'shipping_rates': shipping_rates,
        'show_address_form': show_address_form,
        'shipping_error': shipping_error,
        'shipping_info': shipping_info,
        'selected_shipping_rate': selected_shipping_rate,
        'selected_shipping_cost': selected_shipping_cost,  # Costo de envío seleccionado
        'selected_shipping_cost_formateado': format_price(selected_shipping_cost)  # Formateado: "3.970,20"
    })

@login_required
def verificar_pago(request, payment_id):
    try:
        sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)
        payment_info = sdk.payment().get(payment_id)
        
        if payment_info["response"]["status"] == "approved":
            return redirect('compra_exitosa')
        else:
            messages.error(request, "El pago no pudo ser procesado")
            return redirect('proceder_pago')
    except mercadopago.exceptions.MPError as e:
        logger.error(f"Error de MercadoPago al verificar pago: {str(e)}")
        messages.error(request, "Error al verificar el estado del pago")
        return redirect('proceder_pago')
    except Exception as e:
        logger.error(f"Error inesperado al verificar pago: {str(e)}")
        messages.error(request, "Error interno al verificar el pago")
        return redirect('proceder_pago')