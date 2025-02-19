#!/usr/bin/env python3
import asyncio
import websockets
import json
import configparser
import logging
import random
from logging.handlers import RotatingFileHandler
__version__ = '1.3.8'

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

# Constantes para reconexión
MAX_RECONNECT_ATTEMPTS = 5
BASE_DELAY = 4  # segundos
MAX_DELAY = 60  # segundos máximos entre intentos

def load_config():
    """
    Carga la configuración desde config.ini con validación mejorada.
    """
    config = configparser.ConfigParser()
    config.read(CONFIG_FILE)

    if "sub_bridge" not in config:
        raise KeyError("La sección [sub_bridge] no existe en config.ini")

    required_fields = ["ip", "port", "sub_bridge_port", "id"]
    config_values = {}
    
    for field in required_fields:
        value = config["sub_bridge"].get(field, "").strip()
        if not value:
            raise ValueError(f"Campo requerido '{field}' falta o está vacío en config.ini")
        config_values[field] = value

    bridge_uri = f"ws://{config_values['ip']}:{config_values['port']}"
    return bridge_uri, int(config_values['sub_bridge_port']), config_values['id']

try:
    BRIDGE_SERVER_URI, SUB_BRIDGE_PORT, SUB_BRIDGE_ID = load_config()
    logger.info(f"[SUB-BRIDGE] Configuración cargada: Puerto {SUB_BRIDGE_PORT}, ID {SUB_BRIDGE_ID}")
except Exception as e:
    logger.critical(f"[SUB-BRIDGE] Error en la configuración: {e}")
    exit(1)

connected_clients = set()
bridge_server_connection = None
bridge_task = None
reconnect_attempts = 0

async def exponential_backoff():
    """
    Calcula el tiempo de espera usando backoff exponencial con jitter.
    """
    global reconnect_attempts
    if reconnect_attempts >= MAX_RECONNECT_ATTEMPTS:
        reconnect_attempts = 0
        return MAX_DELAY
    
    delay = min(BASE_DELAY * (2 ** reconnect_attempts), MAX_DELAY)
    jitter = delay * 0.1  # 10% de jitter
    actual_delay = delay + (random.random() * jitter)
    reconnect_attempts += 1
    
    return actual_delay

async def connect_to_bridge_server():
    """
    Maneja la conexión al bridge_server con reconexión automática y backoff exponencial.
    """
    global bridge_server_connection
    while connected_clients:
        try:
            logger.info(f"[SUB-BRIDGE] Intentando conectar con {BRIDGE_SERVER_URI} ...")
            async with websockets.connect(
                BRIDGE_SERVER_URI,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5
            ) as ws:
                bridge_server_connection = ws
                logger.info("[SUB-BRIDGE] Conectado al bridge_server.")

                # Enviar mensaje de identificación
                identification_message = json.dumps({
                    "action": "sub_bridge_identify",
                    "id": SUB_BRIDGE_ID
                })
                await ws.send(identification_message)
                logger.info(f"[SUB-BRIDGE] Identificación enviada: {SUB_BRIDGE_ID}")

                # Mantener la conexión y procesar mensajes
                try:
                    async for message in ws:
                        logger.debug(f"[SUB-BRIDGE] Mensaje recibido: {message}")
                        await broadcast_message(message)
                except websockets.exceptions.ConnectionClosed as e:
                    logger.warning(f"[SUB-BRIDGE] Conexión cerrada: {e}")
                except Exception as e:
                    logger.error(f"[SUB-BRIDGE] Error procesando mensajes: {e}")

        except asyncio.CancelledError:
            logger.warning("[SUB-BRIDGE] Tarea de conexión cancelada.")
            break
        except Exception as e:
            logger.error(f"[SUB-BRIDGE] Error de conexión: {e}")
        finally:
            bridge_server_connection = None
            logger.info("[SUB-BRIDGE] Desconectado del bridge_server.")

        if connected_clients:
            delay = await exponential_backoff()
            logger.info(f"[SUB-BRIDGE] Reintentando conexión en {delay:.1f} segundos...")
            await asyncio.sleep(delay)

    logger.info("[SUB-BRIDGE] Saliendo de la función de conexión.")

async def manage_bridge_connection():
    """
    Gestiona el ciclo de vida de la conexión al bridge_server.
    """
    global bridge_task
    while True:
        if connected_clients and bridge_task is None:
            logger.info("[SUB-BRIDGE] Iniciando conexión al bridge_server.")
            bridge_task = asyncio.create_task(connect_to_bridge_server())
        elif not connected_clients and bridge_task is not None:
            logger.info("[SUB-BRIDGE] Cancelando conexión al bridge_server.")
            bridge_task.cancel()
            try:
                await bridge_task
            except asyncio.CancelledError:
                pass
            bridge_task = None
        await asyncio.sleep(1)

async def broadcast_message(message: str):
    """
    Distribuye mensajes a los clientes conectados con manejo de errores mejorado.
    """
    to_remove = set()
    for ws in connected_clients.copy():
        try:
            try:
                pong_waiter = await ws.ping()
                await asyncio.wait_for(pong_waiter, timeout=5)
            except Exception as e:
                logger.warning(f"[SUB-BRIDGE] Cliente {ws.remote_address} no responde: {e}")
                to_remove.add(ws)
                continue
                
            await ws.send(message)
            logger.debug(f"[SUB-BRIDGE] Mensaje enviado a {ws.remote_address}")
        except websockets.exceptions.ConnectionClosed:
            logger.warning(f"[SUB-BRIDGE] Conexión cerrada con {ws.remote_address}")
            to_remove.add(ws)
        except Exception as e:
            logger.error(f"[SUB-BRIDGE] Error enviando mensaje a {ws.remote_address}: {e}")
            to_remove.add(ws)

    for ws in to_remove:
        if ws in connected_clients:
            connected_clients.remove(ws)
            logger.info(f"[SUB-BRIDGE] Cliente removido: {ws.remote_address}")

async def forward_message_to_bridge_server(message: str):
    """
    Reenvía mensajes al bridge_server con validación y manejo de errores.
    """
    global bridge_server_connection
    if not bridge_server_connection:
        logger.error("[SUB-BRIDGE] No hay conexión con bridge_server.")
        return

    try:
        # Validar que el mensaje sea JSON válido
        json.loads(message)
        await bridge_server_connection.send(message)
        logger.debug("[SUB-BRIDGE] Mensaje reenviado al bridge_server.")
    except json.JSONDecodeError:
        logger.error("[SUB-BRIDGE] Mensaje no es JSON válido.")
    except Exception as e:
        logger.error(f"[SUB-BRIDGE] Error enviando mensaje al bridge_server: {e}")

async def handler(websocket):
    """
    Maneja las conexiones de clientes individuales.
    """
    client_info = f"{websocket.remote_address}"
    logger.info(f"[SUB-BRIDGE] Nuevo cliente conectado: {client_info}")
    
    connected_clients.add(websocket)
    try:
        async for message in websocket:
            logger.debug(f"[SUB-BRIDGE] Mensaje de {client_info}: {message}")
            await forward_message_to_bridge_server(message)
    except websockets.exceptions.ConnectionClosed:
        logger.info(f"[SUB-BRIDGE] Cliente desconectado normalmente: {client_info}")
    except Exception as e:
        logger.error(f"[SUB-BRIDGE] Error con cliente {client_info}: {e}")
    finally:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        logger.info(f"[SUB-BRIDGE] Cliente removido: {client_info}")

async def main():
    """
    Función principal que inicia el servidor.
    """
    try:
        server = await websockets.serve(
            handler,
            "0.0.0.0",
            SUB_BRIDGE_PORT,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=5
        )
        logger.info(f"[SUB-BRIDGE] Servidor WebSocket en ws://0.0.0.0:{SUB_BRIDGE_PORT}")
        
        # Ejecutar las tareas principales
        await asyncio.gather(
            manage_bridge_connection(),
            server.wait_closed()
        )
    except Exception as e:
        logger.critical(f"[SUB-BRIDGE] Error crítico en el servidor: {e}", exc_info=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("[SUB-BRIDGE] Servidor detenido manualmente.")
    except Exception as e:
        logger.critical(f"[SUB-BRIDGE] Error crítico: {e}", exc_info=True)
