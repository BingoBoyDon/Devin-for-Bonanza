#!/usr/bin/python3
import grpc
import requests
import time
import uuid
import netifaces
import test_pb2
import test_pb2_grpc
import subprocess
import configparser
import re
from concurrent.futures import ThreadPoolExecutor
import os
import pwd
import tarfile
import shutil
import json

__version__ = '1.1.0'
# Leer el archivo de configuración
config = configparser.ConfigParser()
config.read('config.ini')

# Obtener configuración de config.ini
use_server_mac_confirmation = config.getboolean('settings', 'use_server_mac_confirmation', fallback=True)
server_ip = config.get('server', 'ip', fallback='localhost')
server_port = config.get('server', 'port', fallback='50051')

# Parámetros para los canales gRPC persistentes
CHANNEL_OPTIONS = [
    ('grpc.keepalive_time_ms', 10000),
    ('grpc.keepalive_timeout_ms', 5000),
    ('grpc.keepalive_permit_without_calls', True),
    ('grpc.http2.max_pings_without_data', 0),
    ('grpc.http2.min_time_between_pings_ms', 5000),
    ('grpc.http2.min_ping_interval_without_data_ms', 5000)
]

def get_public_ip():
    """Obtiene la dirección IP pública del cliente."""
    try:
        response = requests.get('https://api.ipify.org')
        return response.text
    except requests.RequestException as e:
        print(f"Error obteniendo la IP pública: {e}")
        return "Unknown"

def get_first_mac_address():
    """Obtiene la dirección MAC de la primera interfaz de red que no es loopback."""
    try:
        interfaces = netifaces.interfaces()
        for interface in interfaces:
            if interface != 'lo':  # Excluir loopback
                addrs = netifaces.ifaddresses(interface)
                if netifaces.AF_LINK in addrs:
                    mac_address = addrs[netifaces.AF_LINK][0]['addr']
                    if mac_address:
                        print(f"Usando dirección MAC {mac_address} de la interfaz {interface}")
                        return mac_address
        return "00:00:00:00:00:00"
    except Exception as e:
        print(f"Error obteniendo la dirección MAC: {e}")
        return "00:00:00:00:00:00"

def run_server_mac():
    """Ejecuta el script server_mac.py para validar la dirección MAC."""
    try:
        result = subprocess.run(["python3", "server_mac.py"], capture_output=True, text=True)
        output = result.stdout
        if "OK hash" in output:
            print("server_mac.py: OK hash")
            return True
        elif "Fail hash" in output:
            print("server_mac.py: Fail hash")
            return False
        else:
            return None
    except subprocess.CalledProcessError as e:
        print(f"Error ejecutando server_mac.py: {e}")
        return None

def determine_mac_to_send():
    """Determina qué dirección MAC enviar según la configuración y validación del servidor."""
    if use_server_mac_confirmation:
        print("Usando server_mac.py para validación de MAC...")
        result = run_server_mac()
        if result is True:
            return get_first_mac_address()  # Usar la primera MAC válida si el hash es correcto
        elif result is False:
            return "00:00:00:00:00:00"  # Enviar MAC de ceros si el hash falla
        else:
            return get_first_mac_address()  # Enviar la primera MAC válida si no hay resultado
    else:
        print("Omitiendo validación de server_mac.py, usando la primera MAC válida...")
        return get_first_mac_address()

def generate_requests():
    """Genera solicitudes de conexión con información del cliente."""
    public_ip = get_public_ip()
    mac_address = determine_mac_to_send()
    # Usar la primera MAC válida como client_id
    client_id = mac_address
    yield test_pb2.ConnectionRequest(client_id=client_id, public_ip=public_ip, mac_address=mac_address)

def get_keys(client_id):
    """Solicita el archivo comprimido de llaves al servidor y lo procesa localmente."""
    try:
        channel = grpc.insecure_channel(f'{server_ip}:{server_port}', options=CHANNEL_OPTIONS)
        stub = test_pb2_grpc.TestServiceStub(channel)
        print("Solicitando llaves al servidor...")
        request = test_pb2.KeyFilesRequest(client_id=client_id)
        response = stub.GetKeys(request)
        if response.host_keys:
            temp_tar_path = '/home/bonanza/.ssh/host_keys.tar.gz'
            with open(temp_tar_path, 'wb') as f:
                f.write(response.host_keys)
            print(f"Archivo host_keys.tar.gz guardado en {temp_tar_path}")

            try:
                with tarfile.open(temp_tar_path, 'r:gz') as tar:
                    tar.extractall(path='/home/bonanza/.ssh')
                print("Llaves extraídas exitosamente en /home/bonanza/.ssh")

                ssh_dir = '/home/bonanza/.ssh'
                id_rsa_path = os.path.join(ssh_dir, 'id_rsa')
                id_rsa_cert_pub_path = os.path.join(ssh_dir, 'id_rsa-cert.pub')
                id_rsa_pub_path = os.path.join(ssh_dir, 'id_rsa.pub')

                os.chmod(id_rsa_path, 0o600)
                os.chmod(id_rsa_cert_pub_path, 0o600)
                os.chmod(id_rsa_pub_path, 0o644)

                user_info = pwd.getpwnam('bonanza')
                os.chown(id_rsa_path, user_info.pw_uid, user_info.pw_gid)
                os.chown(id_rsa_cert_pub_path, user_info.pw_uid, user_info.pw_gid)
                os.chown(id_rsa_pub_path, user_info.pw_uid, user_info.pw_gid)

                print("Permisos y propiedad de las llaves en ~/.ssh establecidas correctamente.")

                host_keys = [
                    'ssh_host_ed25519_key',
                    'ssh_host_rsa_key',
                    'ssh_host_ed25519_key-cert.pub',
                    'ssh_host_rsa_key-cert.pub'
                ]
                for key_file in host_keys:
                    src = os.path.join(ssh_dir, key_file)
                    dest = os.path.join('/etc/ssh', key_file)
                    try:
                        subprocess.run(['sudo', '/usr/bin/mv', src, dest], check=True)
                        print(f"{key_file} movido a /etc/ssh/ exitosamente.")
                    except subprocess.CalledProcessError as e:
                        print(f"Error moviendo {key_file} a /etc/ssh/: {e}")

                for key_file in host_keys:
                    dest = os.path.join('/etc/ssh', key_file)
                    try:
                        subprocess.run(['sudo', '/usr/bin/chown', 'root:root', dest], check=True)
                        print(f"Propiedad de {key_file} cambiada a root:root.")
                    except subprocess.CalledProcessError as e:
                        print(f"Error cambiando propiedad de {key_file}: {e}")

                try:
                    subprocess.run(['sudo', '/usr/bin/chmod', '600', '/etc/ssh/ssh_host_ed25519_key'], check=True)
                    subprocess.run(['sudo', '/usr/bin/chmod', '600', '/etc/ssh/ssh_host_rsa_key'], check=True)
                    subprocess.run(['sudo', '/usr/bin/chmod', '644', '/etc/ssh/ssh_host_ed25519_key-cert.pub'], check=True)
                    subprocess.run(['sudo', '/usr/bin/chmod', '644', '/etc/ssh/ssh_host_rsa_key-cert.pub'], check=True)
                    print("Permisos de host keys establecidos correctamente en /etc/ssh/.")
                except subprocess.CalledProcessError as e:
                    print(f"Error estableciendo permisos de host keys: {e}")

                os.remove(temp_tar_path)
                print("Llaves procesadas y archivo temporal eliminado.")

                verify_public_key(id_rsa_pub_path, client_id)

            except Exception as e:
                print(f"Error extrayendo host_keys.tar.gz: {e}")
        else:
            print("No se recibieron llaves del servidor.")
    except grpc.RpcError as e:
        print(f"Error solicitando llaves: {e.details()}")

def verify_public_key(pub_key_path, client_id):
    """Verifica que la llave pública recibida coincida con la esperada."""
    try:
        with open(pub_key_path, 'rb') as f:
            pub_key_content = f.read().strip()
        if pub_key_content.startswith(b"ssh-rsa"):
            print(f"Llave pública {pub_key_path} verificada exitosamente.")
        else:
            print(f"Llave pública {pub_key_path} no es válida.")
    except Exception as e:
        print(f"Error verificando la llave pública {pub_key_path}: {e}")

def move_image_with_retries(temp_image_path, final_image_path, retries=5, delay=5):
    """Intenta mover una imagen del directorio temporal al destino final, con reintentos en caso de error."""
    attempt = 0
    while attempt < retries:
        try:
            shutil.move(temp_image_path, final_image_path)
            print(f"Imagen {temp_image_path} movida a {final_image_path}")
            return True
        except Exception as e:
            print(f"Error moviendo {temp_image_path} a {final_image_path}: {e}")
            attempt += 1
            if attempt < retries:
                print(f"Reintentando mover la imagen en {delay} segundos... (Intento {attempt}/{retries})")
                time.sleep(delay)
            else:
                print(f"Falló el movimiento de la imagen después de {retries} intentos.")
                return False

def get_bingo_images(client_id):
    """Solicita imágenes de bingo al servidor y las procesa."""
    config.read('config.ini')
    temp_dir = '/tmp/bingo_images'
    mount_point = config.get('mount', 'mount_point', fallback='/mnt/windows_shared')
    try:
        channel = grpc.insecure_channel(f'{server_ip}:{server_port}', options=CHANNEL_OPTIONS)
        stub = test_pb2_grpc.TestServiceStub(channel)
        print("Solicitando imágenes de bingo al servidor...")
        request = test_pb2.ImageRequest(client_id=client_id)
        responses = stub.GetBingoImages(request)
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir, mode=0o755)
            print(f"Directorio temporal creado en {temp_dir}")
        for response in responses:
            image_name = response.image_name
            image_data = response.image_data
            temp_image_path = os.path.join(temp_dir, image_name)
            with open(temp_image_path, 'wb') as f:
                f.write(image_data)
            print(f"Imagen {image_name} descargada temporalmente en {temp_image_path}")
            user_info = pwd.getpwnam('bonanza')
            os.chown(temp_image_path, user_info.pw_uid, user_info.pw_gid)
            os.chmod(temp_image_path, 0o644)
            final_image_path = os.path.join(mount_point, image_name)
            if not move_image_with_retries(temp_image_path, final_image_path):
                print(f"Error permanente al mover {image_name}. Continuando con las siguientes imágenes...")
        if not os.listdir(temp_dir):
            os.rmdir(temp_dir)
            print(f"Directorio temporal {temp_dir} eliminado.")
    except grpc.RpcError as e:
        print(f"Error solicitando imágenes: {e.details()}")
    except Exception as e:
        print(f"Error durante el procesamiento de imágenes: {e}")

def keys_exist():
    """Verifica si las llaves id_rsa, id_rsa-cert.pub e id_rsa.pub existen en el directorio .ssh."""
    ssh_dir = '/home/bonanza/.ssh'
    id_rsa_path = os.path.join(ssh_dir, 'id_rsa')
    id_rsa_cert_pub_path = os.path.join(ssh_dir, 'id_rsa-cert.pub')
    id_rsa_pub_path = os.path.join(ssh_dir, 'id_rsa.pub')
    return all([
        os.path.isfile(id_rsa_path),
        os.path.isfile(id_rsa_cert_pub_path),
        os.path.isfile(id_rsa_pub_path)
    ])

# --- STREAMING con canal persistente ---

def listen_for_bingo_numbers(client_id):
    """Escucha números de bingo desde el servidor y los procesa usando un canal persistente."""
    channel = grpc.insecure_channel(f'{server_ip}:{server_port}', options=CHANNEL_OPTIONS)
    stub = test_pb2_grpc.TestServiceStub(channel)
    request = test_pb2.BingoNumbersRequest(client_id=client_id)
    while True:
        try:
            for response in stub.StreamBingoNumbers(request):
                numbers = response.numbers
                draw_id = response.draw_id
                print(f"Números de bingo recibidos del servidor: {numbers}, Draw ID: {draw_id}")

                try:
                    result = subprocess.run(
                        ["python3", "/home/bonanza/azkiosk_client/send_ball_numbers.py"] + list(map(str, numbers)),
                        capture_output=True,
                        text=True
                    )
                except Exception as e:
                    print(f"Error ejecutando send_ball_numbers.py: {e}")
                    result = subprocess.CompletedProcess(args=[], returncode=1, stdout='', stderr=str(e))

                print("Solicitando imágenes de bingo después de recibir los números.")
                get_bingo_images(client_id)

                success = result.returncode == 0
                details = "The ball draw was successfully set." if success else f"Error: {result.stderr.strip()}"
                confirmation_request = test_pb2.ConfirmationRequest(
                    client_id=client_id,
                    success=success,
                    details=details,
                    draw_id=draw_id
                )
                try:
                    confirmation_response = stub.ConfirmReceipt(confirmation_request)
                    print(f"Confirmación enviada: {confirmation_response.message}")
                except grpc.RpcError as e:
                    print(f"Error enviando confirmación: {e.details()}")
        except grpc.RpcError as e:
            print(f"Error al recibir números de bingo: {e}")
            time.sleep(5)

def listen_for_commands(client_id):
    """Escucha códigos de comando desde el servidor y los ejecuta usando un canal persistente."""
    channel = grpc.insecure_channel(f'{server_ip}:{server_port}', options=CHANNEL_OPTIONS)
    stub = test_pb2_grpc.TestServiceStub(channel)
    request = test_pb2.CommandRequest(client_id=client_id)
    while True:
        try:
            for response in stub.StreamCommandCodes(request):
                command_code = response.command_code
                sent_at = response.sent_at
                print(f"Código de comando {command_code} recibido del servidor enviado en {sent_at}")

                try:
                    result = subprocess.run(
                        ["python3", "/home/bonanza/webserver_client/command_executor.py", str(command_code)],
                        capture_output=True,
                        text=True
                    )
                    if result.returncode == 0:
                        print(f"Comando {command_code} ejecutado exitosamente.")
                    else:
                        print(f"Error ejecutando el comando {command_code}: {result.stderr}")
                except Exception as e:
                    print(f"Error ejecutando el comando {command_code}: {e}")
        except grpc.RpcError as e:
            print(f"Error al recibir códigos de comando: {e}")
            time.sleep(5)

def send_error_confirmation(stub, client_id, adjustment_id, error_message, transaction_id=None):
    """Envía una confirmación de error al servidor con el mensaje de error."""
    # Códigos de error específicos para diferentes tipos de errores
    # -1: Account not found
    # -2: Connection reset by peer
    # -3: No route to host
    # -4: Unknown error
    # -5: Account in use
    
    error_code = -4  # Default: Unknown error
    error_type = "Unknown Error"
    
    if "Account not found" in error_message:
        error_code = -1
        error_type = "Account Not Found"
    elif "Connection reset by peer" in error_message:
        error_code = -2
        error_type = "Connection Reset"
    elif "No route to host" in error_message:
        error_code = -3
        error_type = "No Route to Host"
    elif "Account is currently in use" in error_message:
        error_code = -5
        error_type = "Account In Use"
    
    print(f"Enviando confirmación de error al servidor. Tipo: {error_type}, Código: {error_code}, ID: {adjustment_id}, Mensaje: {error_message}")
    
    # Enviar confirmación al servidor con valores específicos para cada tipo de error
    confirm_req = test_pb2.BalanceAdjustmentConfirmation(
        client_id=client_id,
        adjustment_id=adjustment_id,
        previous_balance=error_code,
        new_balance=error_code
    )
    try:
        confirm_resp = stub.ConfirmBalanceAdjustment(confirm_req)
        print(f"Confirmación de error recibida: {confirm_resp.message}, Transaction ID: {transaction_id if transaction_id else 0}")
    except grpc.RpcError as e:
        print(f"Error enviando confirmación de error: {e.details()}")

def listen_for_balance_adjustments(client_id):
    """Escucha solicitudes de ajuste de balance, ejecuta el ajuste y envía la confirmación con ambos balances."""
    
    channel = grpc.insecure_channel(f'{server_ip}:{server_port}', options=CHANNEL_OPTIONS)
    stub = test_pb2_grpc.TestServiceStub(channel)
    request = test_pb2.BalanceAdjustmentQuery(client_id=client_id)

    while True:
        try:
            for adjustment_request in stub.StreamBalanceAdjustment(request):
                print(f"Solicitud de ajuste recibida: {adjustment_request}")

                # Ejecutar el script de ajuste en modo unbuffered (-u) para forzar el flush de stdout
                # Solo enviamos el número de teléfono, la cantidad a ajustar y el adjustment_id
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
                    error_message = f"Error ejecutando balance_adjustment_client.py: {e}"
                    print(error_message)
                    # Enviar confirmación de error al servidor
                    send_error_confirmation(stub, client_id, adjustment_request.adjustment_id, error_message)
                    continue

                # Mostrar datos de depuración para verificar la salida
                print("DEBUG: returncode =", result.returncode)
                print("DEBUG: stdout =", result.stdout)
                print("DEBUG: stderr =", result.stderr)

                if result.returncode == 0:
                    try:
                        output = result.stdout.strip()
                        data = json.loads(output)
                        # Obtener el balance inicial y final del JSON devuelto por balance_adjustment_client.py
                        previous_balance = data["previous_balance"]
                        new_balance = data["new_balance"]
                        
                        # Extraer el Transaction ID del stderr si está disponible
                        transaction_id = 0
                        stderr_output = result.stderr.strip()
                        transaction_id_match = re.search(r'Transaction ID: ([-\d]+)', stderr_output)
                        if transaction_id_match:
                            transaction_id = int(transaction_id_match.group(1))
                            print(f"Transaction ID extraído: {transaction_id}")
                        
                    except Exception as e:
                        error_message = f"Error al parsear el output: {e}"
                        print(error_message)
                        # Enviar confirmación de error al servidor
                        send_error_confirmation(stub, client_id, adjustment_request.adjustment_id, error_message)
                        continue
                    print(f"Ajuste completado. Balance inicial: {previous_balance} cents, Nuevo balance: {new_balance} cents")

                    # Enviar confirmación al servidor usando los balances obtenidos del script
                    confirm_req = test_pb2.BalanceAdjustmentConfirmation(
                        client_id=client_id,
                        adjustment_id=adjustment_request.adjustment_id,
                        previous_balance=previous_balance,
                        new_balance=new_balance
                    )
                    print(f"Enviando confirmación al servidor: AdjustmentID: {adjustment_request.adjustment_id}, Balance Inicial: {previous_balance}, Nuevo Balance: {new_balance}, Transaction ID: {transaction_id}")
                    try:
                        confirm_resp = stub.ConfirmBalanceAdjustment(confirm_req)
                        print(f"Confirmación recibida: {confirm_resp.message}, Transaction ID: {transaction_id}")
                    except grpc.RpcError as e:
                        print(f"Error enviando confirmación: {e.details()}")
                else:
                    # Extraer el mensaje de error del stderr
                    error_message = result.stderr.strip()
                    print(f"Error en balance_adjustment_client.py: {error_message}")
                    # Enviar confirmación de error al servidor
                    send_error_confirmation(stub, client_id, adjustment_request.adjustment_id, error_message)
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
