import requests
import base64
import json
import logging
from django.conf import settings
from datetime import datetime, timedelta
from decimal import Decimal

# Configurar logging
logger = logging.getLogger(__name__)

class MiCorreoAPI:
    def __init__(self):
        self.base_url = settings.MICORREO_API_BASE_URL
        self.username = settings.MICORREO_API_USERNAME
        self.password = settings.MICORREO_API_PASSWORD
        self.token = None
        self.token_expires = None
        self.cart_total = Decimal('0')  # Changed to Decimal for better precision

    def set_cart_total(self, total):
        """Set the cart total for price validation."""
        # Convert to Decimal if it's not already
        if not isinstance(total, Decimal):
            total = Decimal(str(total))
        self.cart_total = total
        logger.info(f"Cart total set to: ${total}")

    def get_token(self):
        """Obtiene un token JWT usando Basic Auth."""
        if self.token and self.token_expires > datetime.now():
            return self.token

        credentials = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json"
        }
        
        try:
            logger.info(f"Solicitando token a {self.base_url}/token")
            response = requests.post(f"{self.base_url}/token", headers=headers)
            logger.info(f"Respuesta de token: Status={response.status_code}, Contenido={response.text[:100]}...")
            
            if response.status_code == 200:
                data = response.json()
                self.token = data["token"]
                self.token_expires = datetime.strptime(data["expire"], "%Y-%m-%d %H:%M:%S") - timedelta(minutes=5)
                return self.token
            else:
                logger.error(f"Error obteniendo token: {response.status_code} - {response.text}")
                raise Exception(f"Error obteniendo token: {response.status_code} - {response.json().get('message', 'Desconocido')}")
        except Exception as e:
            logger.error(f"Excepción al obtener token: {str(e)}")
            raise Exception(f"Error al conectar con MiCorreo API: {str(e)}")

    def make_request(self, method, endpoint, data=None, params=None, retry=True):
        """Realiza una solicitud autenticada a la API con reintento en caso de error de token."""
        try:
            token = self.get_token()
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            url = f"{self.base_url}/{endpoint}"
            
            logger.info(f"Solicitud {method} a {url}")
            if data:
                logger.info(f"Datos enviados: {json.dumps(data, indent=2)}")
            
            if method == "POST":
                response = requests.post(url, json=data, headers=headers)
            elif method == "GET":
                response = requests.get(url, params=params, headers=headers)
            else:
                raise ValueError("Método no soportado")
            
            logger.info(f"Respuesta {response.status_code}: {response.text[:200]}...")
            
            if response.status_code == 401 and retry:
                logger.warning("Token expirado o inválido, obteniendo uno nuevo")
                self.token = None
                return self.make_request(method, endpoint, data, params, retry=False)
            
            if response.status_code in [200, 202]:
                return response
            else:
                logger.warning(f"La solicitud retornó un código de estado no esperado: {response.status_code}")
                return response
            
        except Exception as e:
            logger.error(f"Excepción en solicitud {method} a {endpoint}: {str(e)}")
            raise

    def register_user(self, user_data):
        """Registra un usuario en MiCorreo."""
        required_fields = ['firstName', 'lastName', 'email', 'password', 'documentType', 'documentId', 'address']
        for field in required_fields:
            if field not in user_data:
                raise ValueError(f"Campo requerido ausente: {field}")
                
        if 'address' in user_data:
            for field in ['streetName', 'streetNumber', 'city', 'provinceCode', 'postalCode']:
                if field not in user_data['address']:
                    raise ValueError(f"Campo de dirección requerido ausente: {field}")
                    
        return self.make_request("POST", "register", data=user_data)

    def get_shipping_rates(self, rate_data):
        """Obtiene cotización de envío con validación adicional."""
        try:
            required_fields = ['customerId', 'postalCodeOrigin', 'postalCodeDestination', 'dimensions']
            for field in required_fields:
                if field not in rate_data:
                    raise ValueError(f"Campo requerido ausente: {field}")
            
            if 'dimensions' in rate_data:
                for dim in ['weight', 'height', 'width', 'length']:
                    if dim not in rate_data['dimensions']:
                        raise ValueError(f"Dimensión requerida ausente: {dim}")
                    value = rate_data['dimensions'][dim]
                    if not isinstance(value, (int, float)) or value <= 0:
                        raise ValueError(f"Dimensión inválida: {dim} debe ser un número positivo")
            
            # NO agregamos cartTotal a rate_data, pero mantenemos self.cart_total
            # para validar internamente las tarifas recibidas después
            logger.info(f"Usando cartTotal: ${self.cart_total} para validación interna de tarifas")
            
            response = self.make_request("POST", "rates", data=rate_data)
            
            if response.status_code in [200, 202]:
                try:
                    response_data = response.json()
                    
                    if 'rates' in response_data and response_data['rates']:
                        num_original_rates = len(response_data['rates'])
                        logger.info(f"Tarifas recibidas: {json.dumps(response_data['rates'], indent=2)}")
                        
                        # Validar cada tarifa
                        valid_rates = []
                        for rate in response_data['rates']:
                            validated_rate = self.validate_shipping_rate(rate)
                            if validated_rate:
                                valid_rates.append(validated_rate)
                        
                        # Actualizar las tarifas en la respuesta
                        response_data['rates'] = valid_rates
                        logger.info(f"Tarifas de envío validadas: {len(valid_rates)} de {num_original_rates} opciones válidas")
                        
                        # Actualizar la respuesta con las tarifas validadas
                        response._content = json.dumps(response_data).encode('utf-8')
                        return response
                    else:
                        logger.warning(f"La respuesta no contiene tarifas: {response_data}")
                except Exception as e:
                    logger.error(f"Error al procesar respuesta JSON: {str(e)}")
            
            return response
        except Exception as e:
            logger.error(f"Error al obtener tarifas de envío: {str(e)}")
            raise

    def import_shipping(self, shipping_data):
        """Importa un envío a MiCorreo."""
        try:
            required_fields = ['customerId', 'sender', 'recipient', 'shipping']
            for field in required_fields:
                if field not in shipping_data:
                    raise ValueError(f"Campo requerido ausente: {field}")
            
            if 'sender' in shipping_data:
                for field in ['name', 'email', 'originAddress']:
                    if field not in shipping_data['sender']:
                        raise ValueError(f"Campo de remitente requerido ausente: {field}")
                
            if 'recipient' in shipping_data:
                for field in ['name', 'email']:
                    if field not in shipping_data['recipient']:
                        raise ValueError(f"Campo de destinatario requerido ausente: {field}")
                        
            if 'shipping' in shipping_data:
                for field in ['deliveryType', 'weight', 'declaredValue']:
                    if field not in shipping_data['shipping']:
                        raise ValueError(f"Campo de envío requerido ausente: {field}")
                        
                if shipping_data['shipping']['deliveryType'] == 'D' and 'address' not in shipping_data['shipping']:
                    raise ValueError("Entrega a domicilio requiere dirección")
            
            return self.make_request("POST", "shipping/import", data=shipping_data)
        except Exception as e:
            logger.error(f"Error al importar envío: {str(e)}")
            raise
        
    def get_customer_by_email(self, email, password="TemporaryPassword123"):
        """Valida un usuario existente y recupera su customerId."""
        try:
            data = {
                "email": email,
                "password": password
            }
            response = self.make_request("POST", "users/validate", data=data)
            if response.status_code in [200, 202]:
                result = response.json()
                if "customerId" in result:
                    logger.info(f"Customer ID encontrado para {email}: {result['customerId']}")
                    return result["customerId"]
                else:
                    logger.warning(f"Respuesta sin customerId: {result}")
            else:
                logger.error(f"Error buscando customerId: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"Excepción al validar usuario en MiCorreo: {str(e)}")
        return None
    
    def validate_shipping_rate(self, rate):
        """
        Valida que una tarifa de envío sea razonable según reglas de negocio.
        Utiliza una estrategia más clara y predecible.
        """
        try:
            # Trabajar con una copia para no modificar el original
            validated_rate = rate.copy()
            
            # Extraer tipo y precio
            delivery_type = validated_rate.get('deliveredType', '')
            product_name = validated_rate.get('productName', 'Desconocido')
            price = Decimal(str(validated_rate.get('price', 0)))
            
            # Configuración de límites (extraídos a constantes)
            MAX_SUCURSAL_PRICE = Decimal('3500')  # Límite para envíos a sucursal
            MAX_DOMICILIO_PRICE = Decimal('8000')  # Límite para envíos a domicilio
            MAX_PERCENTAGE_OF_TOTAL = Decimal('0.30')  # Máximo 30% del total del carrito
            MIN_SUCURSAL_PRICE = Decimal('800')  # Precio mínimo para envíos a sucursal
            MIN_DOMICILIO_PRICE = Decimal('1500')  # Precio mínimo para envíos a domicilio
            
            # Determinar el límite según tipo de entrega
            if delivery_type == 'S':  # Sucursal
                price_limit = MAX_SUCURSAL_PRICE
                min_price = MIN_SUCURSAL_PRICE
                price_type = "sucursal"
            else:  # Domicilio (D)
                price_limit = MAX_DOMICILIO_PRICE
                min_price = MIN_DOMICILIO_PRICE
                price_type = "domicilio"
            
            # Precio original para referencia
            original_price = price
            price_adjusted = False
            
            # 1. Verificar si el precio excede el límite absoluto
            if price > price_limit:
                logger.warning(f"Precio de {price_type} excesivo: ${price} para {product_name}. Ajustando a ${price_limit}")
                price = price_limit
                price_adjusted = True
            
            # 2. Si tenemos un total de carrito, verificar que no sea excesivo como porcentaje
            if self.cart_total > 0 and price > (self.cart_total * MAX_PERCENTAGE_OF_TOTAL):
                max_percent_price = self.cart_total * MAX_PERCENTAGE_OF_TOTAL
                
                # 3. No permitir que el precio baje por debajo del mínimo establecido
                if max_percent_price < min_price:
                    logger.warning(f"Ajuste por porcentaje (${max_percent_price}) menor que mínimo para {price_type} (${min_price}). Usando precio mínimo.")
                    price = min_price
                else:
                    logger.warning(f"Precio excede {MAX_PERCENTAGE_OF_TOTAL*100}% del total (${self.cart_total}): ${price} para {product_name}. Ajustando a ${max_percent_price}")
                    price = max_percent_price
                    
                price_adjusted = True
            
            # 4. Verificar si el precio es menor que el mínimo permitido
            elif price < min_price:
                logger.warning(f"Precio de {price_type} demasiado bajo: ${price} para {product_name}. Ajustando a mínimo ${min_price}")
                price = min_price
                price_adjusted = True
            
            # Actualizar el precio en la tarifa validada
            if price_adjusted:
                validated_rate['price'] = float(price.quantize(Decimal('0.01')))  # Redondear a 2 decimales
                validated_rate['price_original'] = float(original_price.quantize(Decimal('0.01')))  # Guardar original
            
            # Validar tiempos de entrega (asegurarse que sean valores numéricos)
            for time_field in ['deliveryTimeMin', 'deliveryTimeMax']:
                delivery_time = validated_rate.get(time_field)
                if delivery_time is None or not str(delivery_time).isdigit():
                    if time_field == 'deliveryTimeMin':
                        validated_rate[time_field] = "2"  # Valor predeterminado
                    else:
                        validated_rate[time_field] = "5"  # Valor predeterminado
            
            # Retornar la tarifa validada
            return validated_rate
            
        except Exception as e:
            logger.error(f"Error validando tarifa de envío para {rate.get('productName', 'Desconocido')}: {str(e)}")
            return None
