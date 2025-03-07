#!/usr/bin/python3

import os
import sys
import time
import json
import grpc
import psycopg2
import logging
import threading
import subprocess
from concurrent import futures
from datetime import datetime, timedelta

import test_pb2
import test_pb2_grpc

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler("/var/log/bonanza/cloud_server.log"),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Configuración de la base de datos
DB_CONFIG = {
    'dbname': os.environ.get('DB_NAME', 'web'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': os.environ.get('DB_PORT', '5432')
}

# Diccionario para almacenar los clientes conectados
connected_clients = {}
client_streams = {}
client_last_heartbeat = {}
client_lock = threading.Lock()

# Función para verificar si un cliente existe en la base de datos
def client_exists_in_db(mac_address):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM clients WHERE mac_address = %s", (mac_address,))
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        return result is not None
    except Exception as e:
        logger.error(f"Error checking client in DB: {e}")
        return False

# Función para insertar o actualizar un cliente en la base de datos
def insert_or_update_client_in_db(client_id, public_ip, mac_address):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Verificar si el cliente ya existe
        cursor.execute("SELECT id FROM clients WHERE mac_address = %s", (mac_address,))
        result = cursor.fetchone()
        
        if result:
            # Actualizar cliente existente
            cursor.execute("""
                UPDATE clients 
                SET public_ip = %s, updated_at = CURRENT_TIMESTAMP, status = 'online'
                WHERE mac_address = %s
            """, (public_ip, mac_address))
            logger.info(f"Client {client_id} updated in database.")
        else:
            # Insertar nuevo cliente
            cursor.execute("""
                INSERT INTO clients (mac_address, public_ip, created_at, updated_at, status)
                VALUES (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'online')
            """, (mac_address, public_ip))
            logger.info(f"Client {client_id} inserted into database.")
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error inserting/updating client in DB: {e}")
        return False

# Función para actualizar el estado del cliente en la base de datos
def update_client_status(mac_address, status):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE clients 
            SET status = %s, updated_at = CURRENT_TIMESTAMP
            WHERE mac_address = %s
        """, (status, mac_address))
        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"Client {mac_address} status updated to {status} in database.")
        return True
    except Exception as e:
        logger.error(f"Error updating client status in DB: {e}")
        return False

# Función para registrar confirmaciones en la base de datos
def log_confirmation(client_id, draw_id, success, details):
    try:
        # Implementar lógica para registrar confirmaciones
        pass
    except Exception as e:
        logger.error(f"Failed to log confirmation in DB: {e}")

# Función para actualizar el tiempo de respuesta del procesador
def update_processor_response_time(client_id, draw_id, response_time):
    try:
        # Obtener el ID del cliente desde la base de datos
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Buscar el ID del cliente por su MAC
        cursor.execute("SELECT id FROM clients WHERE mac_address = %s", (client_id,))
        client_result = cursor.fetchone()
        
        if not client_result:
            logger.warning(f"Client {client_id} not found in database.")
            cursor.close()
            conn.close()
            return False
        
        client_db_id = client_result[0]
        
        # Actualizar el tiempo de respuesta para este sorteo
        cursor.execute("""
            INSERT INTO processor_response_times (client_id, draw_id, response_time, created_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (client_id, draw_id) 
            DO UPDATE SET response_time = %s, updated_at = CURRENT_TIMESTAMP
        """, (client_db_id, draw_id, response_time, response_time))
        
        conn.commit()
        cursor.close()
        conn.close()
        logger.info(f"Updated response time for client {client_id}, draw {draw_id}: {response_time}ms")
        return True
    except Exception as e:
        logger.error(f"Error updating processor response time: {e}")
        return False

# Función para generar y firmar llaves
def run_generate_and_sign_keys(client_id):
    try:
        # Crear directorio para el cliente si no existe
        client_dir = f"/home/lynxx/client_keys/{client_id}"
        os.makedirs(client_dir, exist_ok=True)
        
        # Ejecutar script para generar llaves
        result = subprocess.run(
            ["/home/lynxx/scripts/generate_and_sign_keys.sh", client_id],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            logger.error(f"Error generating keys for client {client_id}: {result.stderr}")
            return None
        
        # Comprimir las llaves en un archivo tar.gz
        tar_file = f"{client_dir}/keys.tar.gz"
        tar_result = subprocess.run(
            ["tar", "-czf", tar_file, "-C", client_dir, "."],
            capture_output=True,
            text=True
        )
        
        if tar_result.returncode != 0:
            logger.error(f"Error compressing keys for client {client_id}: {tar_result.stderr}")
            return None
        
        # Leer el archivo comprimido
        with open(tar_file, "rb") as f:
            keys_data = f.read()
        
        return keys_data
    except Exception as e:
        logger.error(f"Error in run_generate_and_sign_keys: {e}")
        return None

# Función para monitorear comandos en la base de datos
def monitor_commands():
    while True:
        try:
            # Obtener comandos pendientes de la base de datos
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            
            # Buscar comandos que no han sido enviados
            cursor.execute("""
                SELECT c.id, c.command_code, c.created_at, cl.mac_address
                FROM commands c
                JOIN clients cl ON c.client_id = cl.id
                WHERE c.sent = FALSE AND cl.status = 'online'
                ORDER BY c.created_at ASC
            """)
            
            commands = cursor.fetchall()
            
            for cmd in commands:
                cmd_id, cmd_code, created_at, mac_address = cmd
                
                # Verificar si el cliente está conectado
                with client_lock:
                    if mac_address in client_streams:
                        # Enviar comando al cliente
                        try:
                            client_stream = client_streams[mac_address]
                            response = test_pb2.CommandResponse(
                                command_code=cmd_code,
                                sent_at=created_at.strftime("%Y-%m-%d %H:%M:%S")
                            )
                            client_stream.send(response)
                            
                            # Marcar comando como enviado
                            cursor.execute("""
                                UPDATE commands
                                SET sent = TRUE, sent_at = CURRENT_TIMESTAMP
                                WHERE id = %s
                            """, (cmd_id,))
                            conn.commit()
                            
                            logger.info(f"Command {cmd_code} sent to client {mac_address}")
                        except Exception as e:
                            logger.error(f"Error sending command to client {mac_address}: {e}")
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            logger.error(f"Error in monitor_commands: {e}")
        
        # Esperar antes de la próxima verificación
        time.sleep(5)

# Implementación del servicio gRPC
class TestServiceServicer(test_pb2_grpc.TestServiceServicer):
    def __init__(self):
        # Iniciar el hilo para monitorear comandos
        command_thread = threading.Thread(target=monitor_commands, daemon=True)
        command_thread.start()
        
        # Iniciar el hilo para enviar heartbeats
        heartbeat_thread = threading.Thread(target=self.send_heartbeats, daemon=True)
        heartbeat_thread.start()
    
    def send_heartbeats(self):
        while True:
            with client_lock:
                current_time = time.time()
                clients_to_remove = []
                
                for client_id, last_time in client_last_heartbeat.items():
                    # Si han pasado más de 30 segundos desde el último heartbeat
                    if current_time - last_time > 30:
                        logger.warning(f"Client {client_id} timed out. Removing from active clients.")
                        clients_to_remove.append(client_id)
                        continue
                    
                    # Enviar heartbeat a los clientes activos
                    if client_id in client_streams:
                        try:
                            response = test_pb2.ConnectionResponse(
                                message=f"Heartbeat from server to client {client_id}"
                            )
                            client_streams[client_id].send(response)
                        except Exception as e:
                            logger.error(f"Error sending heartbeat to client {client_id}: {e}")
                            clients_to_remove.append(client_id)
                
                # Eliminar clientes desconectados
                for client_id in clients_to_remove:
                    if client_id in connected_clients:
                        del connected_clients[client_id]
                    if client_id in client_streams:
                        del client_streams[client_id]
                    if client_id in client_last_heartbeat:
                        del client_last_heartbeat[client_id]
                    
                    # Actualizar estado en la base de datos
                    update_client_status(client_id, "offline")
            
            # Esperar antes del próximo heartbeat
            time.sleep(10)
    
    def Connect(self, request_iterator, context):
        client_id = None
        client_stream = None
        
        try:
            for request in request_iterator:
                # Primera solicitud: registrar cliente
                if client_id is None:
                    client_id = request.client_id
                    public_ip = request.public_ip
                    mac_address = request.mac_address
                    
                    logger.info(f"Client {client_id} connecting from {public_ip} with MAC {mac_address}")
                    
                    # Registrar cliente en la base de datos
                    insert_or_update_client_in_db(client_id, public_ip, mac_address)
                    
                    # Registrar cliente en memoria
                    with client_lock:
                        connected_clients[mac_address] = {
                            'client_id': client_id,
                            'public_ip': public_ip,
                            'connected_at': datetime.now()
                        }
                        client_last_heartbeat[mac_address] = time.time()
                        client_stream = context.peer()
                        client_streams[mac_address] = context
                    
                    # Enviar confirmación de registro
                    yield test_pb2.ConnectionResponse(
                        message=f"Client {client_id} registered successfully."
                    )
                
                # Solicitudes posteriores: mantener conexión y procesar mensajes
                else:
                    # Actualizar timestamp del último heartbeat
                    with client_lock:
                        client_last_heartbeat[mac_address] = time.time()
                    
                    # Procesar mensaje del cliente
                    message = request.message if hasattr(request, 'message') else None
                    
                    if message == "ping":
                        logger.debug(f"Received ping from client {client_id}")
                        yield test_pb2.ConnectionResponse(
                            message=f"Message 'ping' from client {client_id} received."
                        )
                    else:
                        # Otros tipos de mensajes pueden ser procesados aquí
                        yield test_pb2.ConnectionResponse(
                            message=f"Message from client {client_id} received."
                        )
        
        except Exception as e:
            logger.error(f"Error in Connect stream for client {client_id}: {e}")
            
            # Marcar cliente como desconectado
            if client_id:
                with client_lock:
                    if mac_address in connected_clients:
                        del connected_clients[mac_address]
                    if mac_address in client_streams:
                        del client_streams[mac_address]
                    if mac_address in client_last_heartbeat:
                        del client_last_heartbeat[mac_address]
                
                # Actualizar estado en la base de datos
                update_client_status(mac_address, "offline")
    
    def SendMessage(self, request, context):
        client_id = request.client_id
        message = request.message
        logger.info(f"Received message from client {client_id}: {message}")
        return test_pb2.MessageResponse(message=f"Message received: {message}")
    
    def ReceiveBingoNumbers(self, request, context):
        client_id = request.client_id
        numbers = request.numbers
        draw_id = request.draw_id
        
        logger.info(f"Received bingo numbers from client {client_id} for draw {draw_id}: {numbers}")
        
        # Aquí se procesarían los números recibidos
        # Por ejemplo, guardarlos en la base de datos
        
        return test_pb2.BingoNumbersResponse(
            message="Numbers received successfully",
            numbers=numbers,
            draw_id=draw_id
        )
    
    def StreamBingoNumbers(self, request, context):
        client_id = request.client_id
        logger.info(f"Client {client_id} subscribed to bingo numbers stream")
        
        # Aquí se implementaría la lógica para enviar números de bingo
        # Por ejemplo, monitorear una tabla en la base de datos
        
        # Este es un ejemplo simple que envía números cada 5 segundos
        count = 0
        while context.is_active():
            count += 1
            # Simular obtención de números desde la base de datos
            numbers = [i for i in range(count, count+5)]
            draw_id = count  # Identificador único para este sorteo
            
            yield test_pb2.BingoNumbersResponse(
                message=f"Draw {draw_id}",
                numbers=numbers,
                draw_id=draw_id
            )
            
            time.sleep(5)
    
    def ConfirmReceipt(self, request, context):
        client_id = request.client_id
        success = request.success
        details = request.details
        draw_id = request.draw_id
        
        logger.info(f"Received confirmation from client {client_id} for draw {draw_id}: Success={success}, Details={details}")
        
        # Registrar confirmación en la base de datos
        log_confirmation(client_id, draw_id, success, details)
        
        return test_pb2.ConfirmationResponse(
            message=f"Confirmation for draw {draw_id} received"
        )
    
    def GetKeys(self, request, context):
        client_id = request.client_id
        logger.info(f"Received key request from client {client_id}")
        
        # Verificar si el cliente existe en la base de datos
        if not client_exists_in_db(client_id):
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details(f"Client {client_id} not found")
            return test_pb2.KeyFilesResponse(
                message=f"Client {client_id} not found",
                host_keys=b""
            )
        
        # Generar y firmar llaves para el cliente
        keys_data = run_generate_and_sign_keys(client_id)
        
        if keys_data is None:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Failed to generate keys")
            return test_pb2.KeyFilesResponse(
                message="Failed to generate keys",
                host_keys=b""
            )
        
        logger.info(f"Keys generated successfully for client {client_id}")
        return test_pb2.KeyFilesResponse(
            message="Keys generated successfully",
            host_keys=keys_data
        )
    
    def GetBingoImages(self, request, context):
        client_id = request.client_id
        logger.info(f"Received bingo images request from client {client_id}")
        
        # Directorio donde se almacenan las imágenes
        images_dir = "/home/lynxx/bingo_images"
        
        try:
            # Listar archivos en el directorio
            image_files = [f for f in os.listdir(images_dir) if f.endswith(('.png', '.jpg', '.jpeg'))]
            
            for image_file in image_files:
                image_path = os.path.join(images_dir, image_file)
                
                # Leer el archivo de imagen
                with open(image_path, "rb") as f:
                    image_data = f.read()
                
                # Enviar la imagen al cliente
                yield test_pb2.ImageResponse(
                    image_name=image_file,
                    image_data=image_data
                )
                
                logger.info(f"Sent image {image_file} to client {client_id}")
        
        except Exception as e:
            logger.error(f"Error sending images to client {client_id}: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Error sending images: {str(e)}")
    
    def StreamCommandCodes(self, request, context):
        client_id = request.client_id
        logger.info(f"Client {client_id} subscribed to command codes stream")
        
        # Registrar el stream para este cliente
        with client_lock:
            client_streams[client_id] = context
        
        # Mantener el stream abierto hasta que el cliente se desconecte
        try:
            while context.is_active():
                time.sleep(1)
        except Exception as e:
            logger.error(f"Error in command stream for client {client_id}: {e}")
        finally:
            # Limpiar cuando el cliente se desconecte
            with client_lock:
                if client_id in client_streams:
                    del client_streams[client_id]
    
    def SendBalanceAdjustmentRequest(self, request, context):
        client_id = request.client_id
        logger.info(f"Received balance adjustment request for client {client_id}")
        
        # Aquí se procesaría la solicitud de ajuste de balance
        # Ahora usando balance_db_updater.py en lugar de acceso directo a la base de datos
        
        return test_pb2.BalanceAdjustmentResponse(
            message="Balance adjustment request received",
            success=True,
            updated_balance=0  # Este valor se actualizará cuando se complete el ajuste
        )
    
    def StreamBalanceAdjustment(self, request, context):
        client_id = request.client_id
        logger.info(f"Client {client_id} subscribed to balance adjustment stream")
        
        # Aquí se implementaría la lógica para enviar solicitudes de ajuste de balance
        # Ahora usando balance_db_updater.py en lugar de acceso directo a la base de datos
        
        try:
            while context.is_active():
                # Preparar datos para consultar ajustes pendientes
                data = {
                    "command": "get_pending",
                    "client_id": client_id
                }
                
                # Llamar al programa de consulta
                import subprocess
                import json
                
                result = subprocess.run(
                    ["python3", "/home/ubuntu/repos/Devin-for-Bonanza/azkiosk_client/balance_db_updater.py"],
                    input=json.dumps(data),
                    text=True,
                    capture_output=True
                )
                
                if result.returncode == 0:
                    try:
                        output = json.loads(result.stdout.strip())
                        if output.get("success", False) and output.get("adjustments"):
                            # Procesar cada ajuste pendiente
                            for adjustment in output.get("adjustments", []):
                                # Enviar solicitud de ajuste al cliente
                                yield test_pb2.BalanceAdjustmentRequest(
                                    client_id=client_id,
                                    costumers_id=adjustment["costumers_id"],
                                    adjustment_id=adjustment["id"],
                                    adjustment_requested_amount=adjustment["amount"],
                                    phone_number=adjustment["phone_number"]
                                )
                                
                                logger.info(f"Sent balance adjustment request to client {client_id}: AdjustmentID {adjustment['id']}, Amount {adjustment['amount']}")
                    except json.JSONDecodeError:
                        logger.error(f"Error parsing output from balance_db_updater.py: {result.stdout}")
                else:
                    logger.error(f"Error running balance_db_updater.py: {result.stderr}")
                
                # Esperar antes de la próxima verificación
                time.sleep(5)
        
        except Exception as e:
            logger.error(f"Error in balance adjustment stream for client {client_id}: {e}")
    def ConfirmBalanceAdjustment(self, request, context):
        client_id = request.client_id
        adjustment_id = request.adjustment_id
        previous_balance = request.previous_balance
        new_balance = request.new_balance
        transaction_id = request.transaction_id if hasattr(request, 'transaction_id') else 0
        error_code = request.error_code if hasattr(request, 'error_code') else 0
        
        logger.info(f"Received balance adjustment confirmation from client {client_id}: AdjustmentID {adjustment_id}, Previous Balance: {previous_balance}, New Balance: {new_balance}, Transaction ID: {transaction_id}, Error Code: {error_code}")
        
        # Si hay un código de error, registrarlo pero no actualizar la base de datos
        if error_code != 0:
            logger.warning(f"Error en ajuste de balance para client {client_id}, adjustment_id {adjustment_id}: código {error_code}")
            return test_pb2.BalanceAdjustmentResponse(message="Error en ajuste de balance", success=False)
        
        try:
            # Preparar datos para el programa de actualización
            data = {
                "adjustment_id": adjustment_id,
                "previous_balance": previous_balance,
                "new_balance": new_balance,
                "transaction_id": transaction_id
            }
            
            # Llamar al programa de actualización
            import subprocess
            import json
            
            result = subprocess.run(
                ["python3", "/home/ubuntu/repos/Devin-for-Bonanza/azkiosk_client/balance_db_updater.py"],
                input=json.dumps(data),
                text=True,
                capture_output=True
            )
            
            if result.returncode == 0:
                try:
                    output = json.loads(result.stdout.strip())
                    if output.get("success", False):
                        logger.info(f"Balance adjustment {adjustment_id} updated successfully in the database.")
                        return test_pb2.BalanceAdjustmentResponse(message="Balance updated successfully", success=True, updated_balance=new_balance)
                    else:
                        logger.error(f"Error updating balance adjustment {adjustment_id} in DB: {output.get('error', 'Unknown error')}")
                except json.JSONDecodeError:
                    logger.error(f"Error parsing output from balance_db_updater.py: {result.stdout}")
            
            logger.error(f"Error running balance_db_updater.py: {result.stderr}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Error updating balance in database")
            return test_pb2.BalanceAdjustmentResponse(message="Failed to update balance", success=False)
        except Exception as e:
            logger.error(f"Error updating balance adjustment {adjustment_id} in DB: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Error updating balance in database")
            return test_pb2.BalanceAdjustmentResponse(message="Failed to update balance", success=False)

# Función principal del servidor
def serve():
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=300),
        options=[
            ('grpc.keepalive_time_ms', 10000),
            ('grpc.keepalive_timeout_ms', 5000),
            ('grpc.keepalive_permit_without_calls', True),
        ]
    )
    test_pb2_grpc.add_TestServiceServicer_to_server(TestServiceServicer(), server)
    server.add_insecure_port('[::]:50051')
    server.start()
    logger.info("Server is running on port 50051...")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()
