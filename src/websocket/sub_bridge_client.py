#!/usr/bin/env python3
import asyncio
import websockets
import json
import configparser
import logging
from logging.handlers import RotatingFileHandler
__version__ = '1.3.9'

# === Configuración de Logging ===
logger = logging.getLogger("SubBridgeServer")
logger.setLevel(logging.DEBUG)

formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

log_file = "sub_bridge_server.log"
handler = RotatingFileHandler(
    log_file, maxBytes=5*1024*1024, backupCount=5
)
handler.setLevel(logging.DEBUG)
handler.setFormatter(formatter)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)

logger.addHandler(handler)
logger.addHandler(console_handler)

# === Cargar Configuración desde config.ini ===
CONFIG_FILE = "/home/bonanza/webserver_client/config.ini"

def load_config():
    """
    Carga la IP, el puerto del bridge_server.py, el puerto del Sub-Bridge y el ID del sub_bridge.
    """
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    if "sub_bridge" not in config:
        raise KeyError("La sección [sub_bridge] no existe en config.ini")

    bridge_ip = config["sub_bridge"].get("ip", "").strip()
    bridge_port = config["sub_bridge"].get("port", "").strip()
    sub_bridge_port = config["sub_bridge"].get("sub_bridge_port", "").strip()
    sub_bridge_id = config["sub_bridge"].get("id", "").strip()

    if not bridge_ip or not bridge_port or not sub_bridge_port or not sub_bridge_id:
        raise ValueError("Faltan valores en la sección [sub_bridge] del config.ini")

    return f"ws://{bridge_ip}:{bridge_port}", int(sub_bridge_port), sub_bridge_id

try:
    BRIDGE_SERVER_URI, SUB_BRIDGE_PORT, SUB_BRIDGE_ID = load_config()
    logger.info(f"[SUB-BRIDGE] Aceptando conexiones en el puerto {SUB_BRIDGE_PORT} con ID {SUB_BRIDGE_ID}")
except Exception as e:
    logger.critical(f"[SUB-BRIDGE] Error en la configuración: {e}")
    exit(1)

connected_clients = set()  # Clientes conectados al sub-bridge
bridge_server_connection = None  # Conexión con el bridge_server.py
bridge_task = None  # Tarea de conexión al bridge_server.py

async def unwrap_message(message_str: str) -> str:
    """
    Unwraps messages with {"id", "data"} structure to make them compatible with the website.
    If the message doesn't have this structure, returns it unchanged.
    """
    try:
        message_dict = json.loads(message_str)
        # Check if the message has the new format with id and data
        if "id" in message_dict and "data" in message_dict and isinstance(message_dict["data"], dict):
            logger.debug(f"[SUB-BRIDGE] Unwrapping message with ID {message_dict['id']}")
            # Return only the data part as a JSON string
            return json.dumps(message_dict["data"])
        # If not in the new format, return the original message
        return message_str
    except json.JSONDecodeError:
        logger.error(f"[SUB-BRIDGE] Error parsing JSON message: {message_str}")
        return message_str
    except Exception as e:
        logger.error(f"[SUB-BRIDGE] Error unwrapping message: {e}")
        return message_str

async def connect_to_bridge_server():
    global bridge_server_connection
    while connected_clients:
        try:
            logger.info(f"[SUB-BRIDGE] Intentando conectar con {BRIDGE_SERVER_URI} ...")
            async with websockets.connect(BRIDGE_SERVER_URI) as ws:
                bridge_server_connection = ws
                logger.info("[SUB-BRIDGE] Conectado al bridge_server.")

                # Enviar mensaje de identificación
                identification_message = json.dumps({
                    "action": "sub_bridge_identify",
                    "id": SUB_BRIDGE_ID
                })
                await ws.send(identification_message)
                logger.info(f"[SUB-BRIDGE] Se envió la identificación: {SUB_BRIDGE_ID}")

                # Mantener la conexión escuchando mensajes
                async for message in ws:
                    logger.info(f"[SUB-BRIDGE] Mensaje recibido desde bridge_server: {message}")
                    try:
                        message_dict = json.loads(message)
                        if "id" in message_dict and "data" in message_dict:
                            logger.info(f"[SUB-BRIDGE] Mensaje con formato nuevo (ID: {message_dict['id']})")
                        else:
                            logger.info("[SUB-BRIDGE] Mensaje con formato original")
                    except:
                        logger.warning("[SUB-BRIDGE] No se pudo analizar el formato del mensaje")
                    await broadcast_message(message)

        except asyncio.CancelledError:
            logger.warning("[SUB-BRIDGE] La tarea de conexión fue cancelada. Saliendo.")
            break
        except Exception as e:
            logger.error(f"[SUB-BRIDGE] Error con bridge_server: {e}")
        finally:
            bridge_server_connection = None
            logger.info("[SUB-BRIDGE] Desconectado del bridge_server.")
        if connected_clients:
            logger.info("[SUB-BRIDGE] Reintentando conexión en 4 segundos...")
            await asyncio.sleep(4)
    logger.info("[SUB-BRIDGE] Saliendo de la función de conexión: no hay clientes o se canceló la tarea.")

async def manage_bridge_connection():
    global bridge_task
    while True:
        if connected_clients and bridge_task is None:
            logger.info("[SUB-BRIDGE] Hay clientes conectados. Iniciando conexión al bridge_server.")
            bridge_task = asyncio.create_task(connect_to_bridge_server())
        elif not connected_clients and bridge_task is not None:
            logger.info("[SUB-BRIDGE] No hay clientes conectados. Cancelando conexión al bridge_server.")
            bridge_task.cancel()
            bridge_task = None
        await asyncio.sleep(1)

async def broadcast_message(message: str):
    to_remove = set()
    # Unwrap the message before broadcasting
    unwrapped_message = await unwrap_message(message)
    
    for ws in connected_clients.copy():
        try:
            await ws.send(unwrapped_message)
            logger.debug(f"[SUB-BRIDGE] Mensaje enviado a {ws.remote_address}: {unwrapped_message}")
        except Exception as e:
            logger.error(f"[SUB-BRIDGE] Error enviando mensaje a {ws.remote_address}: {e}")
            to_remove.add(ws)
    for ws in to_remove:
        connected_clients.remove(ws)
        logger.info(f"[SUB-BRIDGE] Cliente desconectado: {ws.remote_address}")

async def handler(websocket):
    connected_clients.add(websocket)
    logger.info(f"[SUB-BRIDGE] Nuevo cliente conectado: {websocket.remote_address}")
    try:
        async for message in websocket:
            logger.info(f"[SUB-BRIDGE] Mensaje recibido de cliente {websocket.remote_address}: {message}")
            await forward_message_to_bridge_server(message)
    except websockets.exceptions.ConnectionClosed as e:
        logger.warning(f"[SUB-BRIDGE] Cliente desconectado: {websocket.remote_address} ({e})")
    finally:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        logger.info(f"[SUB-BRIDGE] Cliente removido: {websocket.remote_address}")

async def forward_message_to_bridge_server(message: str):
    global bridge_server_connection
    if bridge_server_connection:
        try:
            await bridge_server_connection.send(message)
            logger.info("[SUB-BRIDGE] Mensaje reenviado al bridge_server.")
        except Exception as e:
            logger.error(f"[SUB-BRIDGE] Error enviando mensaje al bridge_server: {e}")

async def main():
    try:
        server = await websockets.serve(handler, "0.0.0.0", SUB_BRIDGE_PORT)
        logger.info(f"[SUB-BRIDGE] Servidor WebSocket en ws://0.0.0.0:{SUB_BRIDGE_PORT}")
        await asyncio.gather(manage_bridge_connection(), server.wait_closed())
    except Exception as e:
        logger.critical(f"[SUB-BRIDGE] Error crítico en el servidor: {e}", exc_info=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[SUB-BRIDGE] Servidor detenido manualmente.")
    except Exception as e:
        logger.critical(f"[SUB-BRIDGE] Error crítico: {e}", exc_info=True)
