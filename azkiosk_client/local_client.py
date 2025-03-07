#!/usr/bin/python3

import os
import sys
import time
import json
import grpc
import socket
import logging
import threading
import subprocess
import re
from concurrent.futures import ThreadPoolExecutor

import test_pb2
import test_pb2_grpc

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler("/var/log/bonanza/local_client.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Configuración del servidor
server_ip = "192.168.3.13"
server_port = "50051"

# Opciones del canal gRPC
CHANNEL_OPTIONS = [
    ('grpc.keepalive_time_ms', 10000),
    ('grpc.keepalive_timeout_ms', 5000),
    ('grpc.keepalive_permit_without_calls', True),
    ('grpc.http2.max_pings_without_data', 0),
    ('grpc.http2.min_time_between_pings_ms', 10000),
    ('grpc.http2.min_ping_interval_without_data_ms', 5000),
]

def get_public_ip():
    """Obtiene la dirección IP pública del cliente."""
    try:
        response = subprocess.check_output(['curl', '-s', 'https://api.ipify.org'])
        return response.decode('utf-8').strip()
    except Exception as e:
        print(f"Error obteniendo IP pública: {e}")
        return "0.0.0.0"

def get_first_mac_address():
    """Obtiene la primera dirección MAC disponible."""
    try:
        # Obtener la primera interfaz de red que no sea lo (loopback)
        interfaces = os.listdir('/sys/class/net/')
        for interface in interfaces:
            if interface != 'lo':
                with open(f'/sys/class/net/{interface}/address', 'r') as f:
                    mac = f.read().strip()
                    if mac:
                        print(f"Usando dirección MAC {mac} de la interfaz {interface}")
                        return mac
        return "00:00:00:00:00:00"
    except Exception as e:
        print(f"Error obteniendo dirección MAC: {e}")
        return "00:00:00:00:00:00"

def run_server_mac():
    """Ejecuta el script server_mac.py para obtener la MAC autorizada."""
    try:
        result = subprocess.run(['/home/bonanza/azkiosk_client/server_mac.py'], 
                               capture_output=True, text=True, check=True)
        mac = result.stdout.strip()
        if mac:
            print(f"MAC obtenida de server_mac.py: {mac}")
            return mac
        else:
            print("server_mac.py no devolvió una MAC válida.")
            return None
    except Exception as e:
        print(f"Error ejecutando server_mac.py: {e}")
        return None

def determine_mac_to_send():
    """Determina qué dirección MAC enviar al servidor."""
    # Intentar obtener la MAC del script server_mac.py
    server_mac = run_server_mac()
    if server_mac:
        return server_mac
    
    # Si no se pudo obtener del script, usar la primera MAC disponible
    print("Omitiendo validación de server_mac.py, usando la primera MAC válida...")
    return get_first_mac_address()

def generate_requests():
    """Genera las solicitudes para el método Connect."""
    client_id = determine_mac_to_send()
    public_ip = get_public_ip()
    
    # Primera solicitud: enviar información del cliente
    yield test_pb2.ConnectionRequest(client_id=client_id, public_ip=public_ip, mac_address=client_id)
    
    # Solicitudes posteriores: mantener la conexión activa
    while True:
        yield test_pb2.ConnectionRequest(client_id=client_id, message="ping")
        time.sleep(10)

def get_keys(client_id):
    """Solicita las llaves al servidor y las guarda localmente."""
    try:
        # Crear directorio .ssh si no existe
        ssh_dir = "/home/bonanza/.ssh"
        os.makedirs(ssh_dir, exist_ok=True)
        
        # Conectar al servidor
        channel = grpc.insecure_channel(f'{server_ip}:{server_port}', options=CHANNEL_OPTIONS)
        stub = test_pb2_grpc.TestServiceStub(channel)
        
        # Solicitar llaves
        print(f"Solicitando llaves para el cliente {client_id}...")
        response = stub.GetKeys(test_pb2.KeyFilesRequest(client_id=client_id))
        
        if not response.host_keys:
            print("No se recibieron llaves del servidor.")
            return False
        
        # Guardar el archivo tar.gz recibido
        tar_path = f"{ssh_dir}/keys.tar.gz"
        with open(tar_path, "wb") as f:
            f.write(response.host_keys)
        
        print(f"Llaves recibidas y guardadas en {tar_path}")
        
        # Descomprimir el archivo
        result = subprocess.run(
            ["tar", "-xzf", tar_path, "-C", ssh_dir],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            print(f"Error descomprimiendo llaves: {result.stderr}")
            return False
        
        print("Llaves descomprimidas correctamente.")
        
        # Verificar la clave pública
        if not verify_public_key(f"{ssh_dir}/id_rsa.pub"):
            print("La clave pública no es válida.")
            return False
        
        # Establecer permisos correctos
        os.chmod(f"{ssh_dir}/id_rsa", 0o600)
        os.chmod(f"{ssh_dir}/id_rsa.pub", 0o644)
        
        # Configurar known_hosts si existe
        known_hosts_path = f"{ssh_dir}/known_hosts"
        if os.path.exists(known_hosts_path):
            os.chmod(known_hosts_path, 0o644)
        
        print("Llaves configuradas correctamente.")
        return True
    
    except grpc.RpcError as e:
        print(f"Error RPC al solicitar llaves: {e}")
        return False
    except Exception as e:
        print(f"Error al procesar llaves: {e}")
        return False

def verify_public_key(pub_key_path):
    """Verifica que la clave pública tenga el formato correcto."""
    try:
        with open(pub_key_path, "r") as f:
            key_content = f.read().strip()
        
        # Verificar formato básico (ssh-rsa AAAA... comentario)
        parts = key_content.split()
        return len(parts) >= 2 and parts[0] in ["ssh-rsa", "ssh-ed25519", "ecdsa-sha2-nistp256"]
    
    except Exception as e:
        print(f"Error verificando clave pública: {e}")
        return False

def move_image_with_retries(src_path, dest_path, max_retries=3):
    """Mueve una imagen con reintentos en caso de error."""
    for attempt in range(max_retries):
        try:
            # Asegurarse de que el directorio destino existe
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            
            # Copiar el archivo
            with open(src_path, 'rb') as src_file:
                with open(dest_path, 'wb') as dest_file:
                    dest_file.write(src_file.read())
            
            print(f"Imagen movida correctamente de {src_path} a {dest_path}")
            return True
        
        except Exception as e:
            print(f"Error moviendo imagen (intento {attempt+1}/{max_retries}): {e}")
            time.sleep(1)
    
    print(f"No se pudo mover la imagen después de {max_retries} intentos")
    return False

def get_bingo_images(client_id):
    """Solicita imágenes de bingo al servidor y las guarda localmente."""
    try:
        # Crear directorio para imágenes si no existe
        images_dir = "/home/bonanza/bingo_images"
        os.makedirs(images_dir, exist_ok=True)
        
        # Conectar al servidor
        channel = grpc.insecure_channel(f'{server_ip}:{server_port}', options=CHANNEL_OPTIONS)
        stub = test_pb2_grpc.TestServiceStub(channel)
        
        # Solicitar imágenes
        print(f"Solicitando imágenes de bingo para el cliente {client_id}...")
        image_request = test_pb2.ImageRequest(client_id=client_id)
        
        # Contador para imágenes recibidas
        image_count = 0
        
        # Procesar stream de imágenes
        for response in stub.GetBingoImages(image_request):
            if not response.image_data:
                print(f"Imagen vacía recibida: {response.image_name}")
                continue
            
            # Guardar la imagen
            image_path = f"{images_dir}/{response.image_name}"
            with open(image_path, "wb") as f:
                f.write(response.image_data)
            
            print(f"Imagen recibida y guardada: {response.image_name}")
            image_count += 1
        
        print(f"Total de imágenes recibidas: {image_count}")
        return image_count > 0
    
    except grpc.RpcError as e:
        print(f"Error RPC al solicitar imágenes: {e}")
        return False
    except Exception as e:
        print(f"Error al procesar imágenes: {e}")
        return False

def keys_exist():
    """Verifica si las llaves SSH ya existen en el sistema."""
    ssh_dir = "/home/bonanza/.ssh"
    key_path = f"{ssh_dir}/id_rsa"
    pub_key_path = f"{ssh_dir}/id_rsa.pub"
    
    # Verificar que existan ambos archivos
    if os.path.exists(key_path) and os.path.exists(pub_key_path):
        # Verificar que la clave pública tenga el formato correcto
        return verify_public_key(pub_key_path)
    
    return False

def listen_for_bingo_numbers(client_id):
    """Escucha números de bingo desde el servidor y los procesa."""
    while True:
        try:
            channel = grpc.insecure_channel(f'{server_ip}:{server_port}', options=CHANNEL_OPTIONS)
            stub = test_pb2_grpc.TestServiceStub(channel)
            request = test_pb2.BingoNumbersRequest(client_id=client_id)
            
            print("Iniciando stream de números de bingo...")
            
            for response in stub.StreamBingoNumbers(request):
                numbers = response.numbers
                draw_id = response.draw_id
                
                print(f"Números de bingo recibidos para sorteo {draw_id}: {numbers}")
                
                # Medir tiempo de procesamiento
                start_time = time.time()
                
                # Aquí se procesarían los números (por ejemplo, enviándolos a una pantalla)
                # Simulamos un procesamiento
                time.sleep(0.5)
                
                # Calcular tiempo de procesamiento
                process_time = int((time.time() - start_time) * 1000)  # en milisegundos
                
                # Enviar confirmación al servidor
                confirm_req = test_pb2.ConfirmationRequest(
                    client_id=client_id,
                    success=True,
                    details=f"Processed in {process_time}ms",
                    draw_id=draw_id
                )
                
                try:
                    confirm_resp = stub.ConfirmReceipt(confirm_req)
                    print(f"Confirmación enviada para sorteo {draw_id}. Respuesta: {confirm_resp.message}")
                except grpc.RpcError as e:
                    print(f"Error enviando confirmación: {e}")
            
            print("Stream de números de bingo terminado.")
            time.sleep(5)
        
        except grpc.RpcError as e:
            print(f"Error en stream de números: {e}")
            time.sleep(5)

def listen_for_commands(client_id):
    """Escucha comandos desde el servidor y los ejecuta."""
    while True:
        try:
            channel = grpc.insecure_channel(f'{server_ip}:{server_port}', options=CHANNEL_OPTIONS)
            stub = test_pb2_grpc.TestServiceStub(channel)
            request = test_pb2.CommandRequest(client_id=client_id)
            
            print("Iniciando stream de comandos...")
            
            for response in stub.StreamCommandCodes(request):
                command_code = response.command_code
                sent_at = response.sent_at
                
                print(f"Comando recibido: {command_code}, enviado a las {sent_at}")
                
                # Procesar el comando según su código
                if command_code == 1:
                    print("Ejecutando comando de reinicio...")
                    reboot_device()
                elif command_code == 2:
                    print("Ejecutando comando de actualización...")
                    # Implementar lógica de actualización
                else:
                    print(f"Comando desconocido: {command_code}")
            
            print("Stream de comandos terminado.")
            time.sleep(5)
        
        except grpc.RpcError as e:
            print(f"Error en stream de comandos: {e}")
            time.sleep(5)

def send_error_confirmation(client_id, adjustment_id, error_code, transaction_id=None):
    """Envía una confirmación de error al servidor con un código específico."""
    channel = grpc.insecure_channel(f'{server_ip}:{server_port}', options=CHANNEL_OPTIONS)
    stub = test_pb2_grpc.TestServiceStub(channel)
    
    # Enviar confirmación al servidor con valores específicos para cada tipo de error
    confirm_req = test_pb2.BalanceAdjustmentConfirmation(
        client_id=client_id,
        adjustment_id=adjustment_id,
        previous_balance=0,  # Valor por defecto para errores
        new_balance=0,       # Valor por defecto para errores
        transaction_id=transaction_id if transaction_id else 0,
        error_code=error_code
    )
    try:
        confirm_resp = stub.ConfirmBalanceAdjustment(confirm_req)
        print(f"Confirmación de error recibida: {confirm_resp.message}, Transaction ID: {transaction_id if transaction_id else 0}")
    except grpc.RpcError as e:
        print(f"Error enviando confirmación de error: {e.details()}")

def listen_for_balance_adjustments(client_id):
    """Escucha solicitudes de ajuste de balance, consulta el balance inicial, ejecuta el ajuste y envía la confirmación con ambos balances."""
    channel = grpc.insecure_channel(f'{server_ip}:{server_port}', options=CHANNEL_OPTIONS)
    stub = test_pb2_grpc.TestServiceStub(channel)
    request = test_pb2.BalanceAdjustmentQuery(client_id=client_id)

    while True:
        try:
            for adjustment_request in stub.StreamBalanceAdjustment(request):
                print(f"Solicitud de ajuste recibida: {adjustment_request}")

                # Ejecutar el script de ajuste en modo unbuffered (-u) para forzar el flush de stdout
                args = [
                    "/home/bonanza/venv/bin/python3",
                    "-u",  # Ejecuta en modo unbuffered
                    "/home/bonanza/azkiosk_client/balance_adjustment_client.py",
                    str(adjustment_request.phone_number),
                    str(adjustment_request.adjustment_requested_amount),
                    str(adjustment_request.adjustment_id),
                    str(adjustment_request.costumers_id)
                ]
                try:
                    result = subprocess.run(args, capture_output=True, text=True)
                except Exception as e:
                    print(f"Error ejecutando balance_adjustment_client.py: {e}")
                    send_error_confirmation(client_id, adjustment_request.adjustment_id, -4)  # -4: Error desconocido
                    continue

                # Mostrar datos de depuración para verificar la salida
                print("DEBUG: returncode =", result.returncode)
                print("DEBUG: stdout =", result.stdout)
                print("DEBUG: stderr =", result.stderr)

                # Extraer el Transaction ID del stderr si está disponible
                transaction_id = 0
                transaction_id_match = re.search(r'Transaction ID: (-?\d+)', result.stderr)
                if transaction_id_match:
                    transaction_id = int(transaction_id_match.group(1))
                    print(f"Transaction ID extraído: {transaction_id}")

                if result.returncode == 0:
                    try:
                        output = result.stdout.strip()
                        data = json.loads(output)
                        # Se asume que balance_adjustment_client.py devuelve un JSON con:
                        # {"previous_balance": <valor>, "new_balance": <valor>}
                        previous_balance = data["previous_balance"]
                        new_balance = data["new_balance"]
                    except Exception as e:
                        print(f"Error al parsear el output: {e}")
                        send_error_confirmation(client_id, adjustment_request.adjustment_id, -4, transaction_id)  # -4: Error desconocido
                        continue
                    print(f"Ajuste completado. Balance inicial: {previous_balance} cents, Nuevo balance: {new_balance} cents")

                    # Enviar confirmación al servidor usando los balances obtenidos del script
                    confirm_req = test_pb2.BalanceAdjustmentConfirmation(
                        client_id=client_id,
                        adjustment_id=adjustment_request.adjustment_id,
                        previous_balance=previous_balance,
                        new_balance=new_balance,
                        transaction_id=transaction_id,
                        error_code=0  # 0 indica éxito
                    )
                    print(f"Enviando confirmación al servidor: AdjustmentID: {adjustment_request.adjustment_id}, Balance Inicial: {previous_balance}, Nuevo Balance: {new_balance}, Transaction ID: {transaction_id}")
                    try:
                        confirm_resp = stub.ConfirmBalanceAdjustment(confirm_req)
                        print(f"Confirmación recibida: {confirm_resp.message}")
                    except grpc.RpcError as e:
                        print(f"Error enviando confirmación: {e.details()}")
                else:
                    # Determinar el tipo de error basado en el mensaje de error
                    error_code = -4  # Valor por defecto: Error desconocido
                    error_message = result.stderr.strip()
                    
                    if "Error finding account" in error_message:
                        if "recvmsg:Connection reset by peer" in error_message:
                            error_code = -2  # Error de conexión reset
                        elif "No route to host" in error_message:
                            error_code = -3  # Error de ruta al host
                        else:
                            error_code = -1  # Error de cuenta no encontrada
                    elif "Account is currently in use" in error_message:
                        error_code = -5  # Cuenta en uso
                    
                    print(f"Error en balance_adjustment_client.py: {error_message}")
                    send_error_confirmation(client_id, adjustment_request.adjustment_id, error_code, transaction_id)
        except grpc.RpcError as e:
            print(f"Error en stream de ajustes: {e}")
            time.sleep(5)

def reboot_device():
    """Reinicia el dispositivo de manera segura."""
    try:
        print("Reiniciando el dispositivo...")
        subprocess.run(['sudo', 'reboot'], check=True)
    except Exception as e:
        print(f"Error al intentar reiniciar el dispositivo: {e}")

def handle_connect(client_id):
    """Maneja la conexión con el servidor mediante el método Connect usando un canal persistente."""
    max_retries = 6
    retry_count = 0
    while True:
        try:
            channel = grpc.insecure_channel(f'{server_ip}:{server_port}', options=CHANNEL_OPTIONS)
            stub = test_pb2_grpc.TestServiceStub(channel)
            responses = stub.Connect(generate_requests())
            print("Conexión establecida con el servidor.")
            for response in responses:
                print(f"Respuesta del servidor: {response.message}")
                if "registered successfully" in response.message or "already registered" in response.message:
                    print("Conexión verificada exitosamente.")
                elif "Heartbeat" in response.message:
                    print("Recibido heartbeat del servidor.")

                try:
                    ping_response = stub.SendMessage(test_pb2.MessageRequest(client_id=client_id, message="ping"))
                    print(f"Ping enviado al servidor. Respuesta: {ping_response.message}")
                    retry_count = 0
                except grpc.RpcError as e:
                    print(f"Error enviando ping al servidor: {e}")
                    retry_count += 1
                    if retry_count >= max_retries:
                        print("Máximo número de intentos alcanzado. Reiniciando el dispositivo...")
                        reboot_device()
                        return
                    else:
                        time.sleep(5)
            print("El stream de Connect ha terminado.")
            retry_count += 1
            if retry_count >= max_retries:
                print("Máximo número de intentos alcanzado. Reiniciando el dispositivo...")
                reboot_device()
                return
            else:
                time.sleep(10)
        except grpc.RpcError as e:
            print(f"Error en la conexión: {e}")
            retry_count += 1
            if retry_count >= max_retries:
                print("Máximo número de intentos alcanzado. Reiniciando el dispositivo...")
                reboot_device()
                return
            else:
                time.sleep(10)

def run():
    """Función principal para establecer conexión y manejar comunicación con el servidor."""
    client_id = determine_mac_to_send()
    executor = ThreadPoolExecutor(max_workers=4)

    # Iniciar el hilo que maneja la conexión y envía pings
    executor.submit(handle_connect, client_id)

    # Verificar si las llaves ya existen
    if keys_exist():
        print("Las llaves ya existen en /home/bonanza/.ssh/. Se omite la solicitud al servidor.")
    else:
        get_keys(client_id)

    # Iniciar hilos para escucha de comandos, números de bingo y ajustes de balance
    executor.submit(listen_for_commands, client_id)
    executor.submit(listen_for_bingo_numbers, client_id)
    executor.submit(listen_for_balance_adjustments, client_id)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Interrupción por teclado. Cerrando el cliente.")

if __name__ == "__main__":
    run()
