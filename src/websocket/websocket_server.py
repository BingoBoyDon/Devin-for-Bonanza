#!/usr/bin/env python3
import asyncio
import websockets
import logging
import json
import time
from collections import defaultdict
from logging.handlers import RotatingFileHandler

__version__ = '1.3.3'

# Configuración del logger
logger = logging.getLogger('websocket_server')
logger.setLevel(logging.DEBUG)

# Handler para archivo con rotación
log_file = 'websocket_server.log'
file_handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5)
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Handler para consola
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# Contador global para identificadores de mensajes
message_id_counter = 0
# Diccionario para mensajes pendientes de confirmación
# Estructura: {message_id: {"mac_id": mac_id, "message": message_with_id, "timestamp": timestamp}}
pending_messages = {}

# Diccionarios para clientes conectados y colas de mensajes
connected_clients = {}
priority_queues = {
    "high": defaultdict(asyncio.Queue),
    "normal": defaultdict(asyncio.Queue),
}

# Diccionario para rastrear clientes que están procesando mensajes pendientes
# Estructura: {mac_id: True/False}
clients_processing_pending = {}

# Filtro para el debugger (opcional)
class MessageFilter(logging.Filter):
    def __init__(self, message_id=None):
        self.message_id = message_id

    def filter(self, record):
        if self.message_id is None:
            return True
        return str(self.message_id) in record.getMessage()

# Para usar el filtro, descomentar y ajustar el ID:
# logger.addFilter(MessageFilter(message_id=123))

async def send_pending_messages(mac_id):
    """Envía mensajes pendientes para un cliente en orden de antigüedad (del más antiguo al más reciente)."""
    if not mac_id in connected_clients:
        logger.warning(f"Cliente {mac_id} no conectado. No se pueden enviar mensajes pendientes.")
        return
        
    # Filtrar mensajes pendientes para este cliente
    client_pending = {
        msg_id: data for msg_id, data in pending_messages.items() 
        if data["mac_id"] == mac_id
    }
    
    if not client_pending:
        logger.info(f"No hay mensajes pendientes para el cliente {mac_id}")
        return
    
    # Marcar que este cliente está procesando mensajes pendientes
    clients_processing_pending[mac_id] = True
    logger.info(f"Cliente {mac_id} comenzó a procesar mensajes pendientes")
    
    try:
        # Ordenar por timestamp (del más antiguo al más reciente)
        sorted_messages = sorted(
            client_pending.items(), 
            key=lambda item: item[1]["timestamp"]
        )
        
        logger.info(f"Enviando {len(sorted_messages)} mensajes pendientes al cliente {mac_id}")
        
        for msg_id, data in sorted_messages:
            try:
                await connected_clients[mac_id].send(json.dumps(data["message"]))
                logger.info(f"Mensaje pendiente {msg_id} enviado a {mac_id}")
            except Exception as e:
                logger.error(f"Error enviando mensaje pendiente {msg_id} a {mac_id}: {e}")
    finally:
        # Desmarcar que este cliente está procesando mensajes pendientes
        clients_processing_pending[mac_id] = False
        logger.info(f"Cliente {mac_id} terminó de procesar mensajes pendientes")

async def handle_client(websocket):
    mac_id = None
    try:
        raw_message = await websocket.recv()
        try:
            client_data = json.loads(raw_message)
            mac_id = client_data.get("mac_id")
        except json.JSONDecodeError:
            logger.error("Invalid JSON received during handshake. Disconnecting client.")
            return

        if not mac_id:
            logger.error("Missing mac_id in initial JSON message. Disconnecting client.")
            return

        logger.info(f"New client connected: {mac_id}")
        connected_clients[mac_id] = websocket
        asyncio.create_task(process_message_queue(mac_id))
        
        # Enviar mensajes pendientes para este cliente
        await send_pending_messages(mac_id)

        async for raw_message in websocket:
            try:
                message = json.loads(raw_message)
                logger.info(f"JSON message received from {mac_id}: {message}")
                # Procesar confirmaciones
                if "confirmation" in message:
                    await handle_confirmation(message)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON received from {mac_id}: {raw_message}")
    except websockets.exceptions.ConnectionClosedError:
        logger.warning(f"Connection closed for {mac_id if mac_id else 'unknown client'}.")
    finally:
        if mac_id:
            # Limpiar el flag de procesamiento si el cliente se desconecta
            if mac_id in clients_processing_pending:
                clients_processing_pending[mac_id] = False
                logger.info(f"Flag de procesamiento limpiado para cliente desconectado: {mac_id}")
            
            if mac_id in connected_clients:
                del connected_clients[mac_id]
                logger.info(f"Client disconnected: {mac_id}")


async def handle_confirmation(confirmation):
    """Procesa confirmaciones recibidas y elimina mensajes de pendientes."""
    message_id = confirmation.get("id")
    if message_id in pending_messages:
        del pending_messages[message_id]
        logger.info(f"Mensaje {message_id} confirmado y eliminado de pendientes.")
    else:
        logger.warning(f"Confirmación recibida para mensaje no pendiente: {message_id}")

async def process_message_queue(mac_id):
    while mac_id in connected_clients:
        try:
            if not priority_queues["high"][mac_id].empty():
                message = await priority_queues["high"][mac_id].get()
                priority_queues["high"][mac_id].task_done()
            elif not priority_queues["normal"][mac_id].empty():
                message = await priority_queues["normal"][mac_id].get()
                priority_queues["normal"][mac_id].task_done()
            else:
                await asyncio.sleep(0.1)
                continue

            client = connected_clients.get(mac_id)
            if client:
                await client.send(json.dumps({"message": message}))
                logger.info(f"JSON message sent to {mac_id}: {message}")
        except Exception as e:
            logger.error(f"Error processing message for {mac_id}: {e}")
            break

async def send_to_client(mac_id, message, priority="normal", requires_confirmation=False):
    global message_id_counter
    if priority not in priority_queues:
        logger.error(f"Invalid priority level: {priority}")
        return

    # Preparar el mensaje
    try:
        message_dict = json.loads(message)
    except json.JSONDecodeError:
        logger.error(f"Error decodificando JSON: {message}")
        return

    # Si el mensaje es para bridge_server.py, agregar identificador único
    if message_dict.get("program") == "bridge_server.py":
        message_id_counter += 1
        message_id = message_id_counter
        message_with_id = {
            "id": message_id,
            "data": message_dict
        }
        
        # Solo almacenar mensajes que requieren confirmación
        if requires_confirmation:
            pending_messages[message_id] = {
                "mac_id": mac_id, 
                "message": message_with_id,
                "timestamp": time.time()
            }
            logger.info(f"Mensaje {message_id} añadido a pendientes para {mac_id} (requiere confirmación)")
        
        # Verificar si el cliente está procesando mensajes pendientes
        if mac_id in connected_clients:
            if mac_id in clients_processing_pending and clients_processing_pending[mac_id]:
                # El cliente está procesando mensajes pendientes, añadir a la cola
                logger.info(f"Cliente {mac_id} está procesando mensajes pendientes. Añadiendo mensaje {message_id} a la cola.")
                await priority_queues[priority][mac_id].put(message_dict)
                return
            else:
                # El cliente no está procesando mensajes pendientes, enviar directamente
                if not requires_confirmation:
                    logger.info(f"Mensaje {message_id} enviado a {mac_id} (no requiere confirmación)")
                
                try:
                    await connected_clients[mac_id].send(json.dumps(message_with_id))
                    logger.info(f"JSON message sent to {mac_id}: {message_with_id}")
                except Exception as e:
                    logger.error(f"Error sending message to {mac_id}: {e}")
        else:
            logger.warning(f"Client {mac_id} is not connected.")
            # Si el cliente no está conectado y el mensaje requiere confirmación,
            # ya está almacenado en pending_messages
    else:
        # Para mensajes que no son para bridge_server.py
        if mac_id in connected_clients:
            if mac_id in clients_processing_pending and clients_processing_pending[mac_id]:
                # El cliente está procesando mensajes pendientes, añadir a la cola
                logger.info(f"Cliente {mac_id} está procesando mensajes pendientes. Añadiendo mensaje a la cola.")
                await priority_queues[priority][mac_id].put(message_dict)
                return
            else:
                # El cliente no está procesando mensajes pendientes, enviar directamente
                try:
                    await connected_clients[mac_id].send(message)
                    logger.info(f"JSON message sent to {mac_id}: {message}")
                except Exception as e:
                    logger.error(f"Error sending message to {mac_id}: {e}")
        else:
            logger.warning(f"Client {mac_id} is not connected.")

async def listen_to_external_program(host="127.0.0.1", port=9999):
    server = await asyncio.start_server(handle_external_connection, host, port)
    logger.info(f"External program TCP server listening on {host}:{port}")
    async with server:
        await server.serve_forever()

async def handle_external_connection(reader, writer):
    try:
        data = await reader.read(1024)
        message = data.decode("utf-8").strip()
        logger.info(f"Message received from external program: {message}")
        parsed_message = json.loads(message)
        mac_id = parsed_message.get("mac_id")
        if mac_id:
            # Extract requires_confirmation field (default to False if not present)
            requires_confirmation = parsed_message.get("requires_confirmation", False)
            logger.info(f"Message requires confirmation: {requires_confirmation}")
            await send_to_client(mac_id, json.dumps(parsed_message), 
                               priority=parsed_message.get("priority", "normal"),
                               requires_confirmation=requires_confirmation)
        else:
            logger.warning("Invalid JSON message format. Missing 'mac_id'.")
    except Exception as e:
        logger.error(f"Error processing external message: {e}")
    finally:
        writer.close()
        await writer.wait_closed()

async def start_server(host="0.0.0.0", port=8765):
    logger.info(f"WebSocket server version {__version__} listening on ws://{host}:{port}")
    async with websockets.serve(handle_client, host, port):
        logger.info("WebSocket server started. Waiting for connections...")
        await asyncio.Future()

async def main():
    await asyncio.gather(
        start_server(),
        listen_to_external_program()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server manually stopped.")
