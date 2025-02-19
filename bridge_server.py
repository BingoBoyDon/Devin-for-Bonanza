#!/usr/bin/env python3
__version__ = '1.3.10'
import asyncio
import websockets
import json
import aiosqlite
import os
import logging
from logging.handlers import RotatingFileHandler

# === IMPORTA EL MDULO DE MEDIA (antes image_handler) ===
from media_handler import (
    init_media_db,
    insert_media_if_not_exists,
    update_media,
    delete_media,
    load_all_media,
    load_all_media_by_container
)

# === Configuracin de Logging ===
logger = logging.getLogger("BridgeServer")
logger.setLevel(logging.DEBUG)  # Nivel de log global

formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

log_file = "bridge_server.log"
handler = RotatingFileHandler(
    log_file,
    maxBytes=5*1024*1024,  # 5 MB
    backupCount=5
)
handler.setLevel(logging.DEBUG)
handler.setFormatter(formatter)
logger.addHandler(handler)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# === Configuracin de la Base de Datos SQLite ===
DB_FILE = "bridge_server.db"

# Variables para clientes y sub_bridge
connected_clients = set()
sub_bridge_clients = {}

# Diccionario para llevar el ndice actual de registros (fotos y videos)
# para cada combinacin de sub_bridge y targetContainer.
media_indices = {}

async def init_db(db_file: str = DB_FILE):
    """
    Inicializa la base de datos SQLite, creando las tablas 'alerts', 'media' y 'media_indices'.
    """
    try:
        async with aiosqlite.connect(db_file, timeout=30) as conn:
            await conn.execute("PRAGMA journal_mode=WAL;")
            # Tabla alerts (sin cambios)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS alerts (
                    cellId TEXT,
                    mac_id TEXT,
                    priority TEXT,
                    program TEXT,
                    plane INTEGER,
                    description TEXT,
                    action TEXT,
                    sequence INTEGER DEFAULT 0,
                    target_id TEXT,
                    PRIMARY KEY (cellId, target_id)
                )
            ''')
            # Tabla media_indices para persistencia de índices
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS media_indices (
                    sub_bridge_id TEXT,
                    target_container TEXT,
                    current_index INTEGER,
                    PRIMARY KEY (sub_bridge_id, target_container)
                )
            ''')
            await conn.commit()
        await init_media_db(db_file)
        logger.info("Base de datos SQLite inicializada correctamente.")
    except Exception as e:
        logger.exception(f"Error inicializando la base de datos SQLite: {e}")

async def get_media_index(sub_bridge_id: str, target_container: str, db_file: str = DB_FILE) -> int:
    """
    Obtiene el índice actual para un sub_bridge y contenedor específicos.
    """
    try:
        async with aiosqlite.connect(db_file, timeout=30) as conn:
            cursor = await conn.cursor()
            await cursor.execute(
                'SELECT current_index FROM media_indices WHERE sub_bridge_id = ? AND target_container = ?',
                (sub_bridge_id, target_container)
            )
            result = await cursor.fetchone()
            return result[0] if result else 0
    except Exception as e:
        logger.error(f"Error obteniendo índice de media: {e}")
        return 0

async def update_media_index(sub_bridge_id: str, target_container: str, index: int, db_file: str = DB_FILE):
    """
    Actualiza o inserta el índice actual para un sub_bridge y contenedor específicos.
    """
    try:
        async with aiosqlite.connect(db_file, timeout=30) as conn:
            await conn.execute('''
                INSERT INTO media_indices (sub_bridge_id, target_container, current_index)
                VALUES (?, ?, ?)
                ON CONFLICT(sub_bridge_id, target_container) 
                DO UPDATE SET current_index = ?
            ''', (sub_bridge_id, target_container, index, index))
            await conn.commit()
            logger.debug(f"Índice actualizado: {sub_bridge_id}, {target_container}, {index}")
    except Exception as e:
        logger.error(f"Error actualizando índice de media: {e}")

async def upsert_alert(message: dict, db_file: str = DB_FILE):
    """
    Inserta o actualiza un registro en la tabla alerts.
    """
    try:
        async with aiosqlite.connect(db_file, timeout=30) as conn:
            cursor = await conn.cursor()
            action = message.get("action")
            if action == "reset":
                sequence = 0
            elif action in ["update", "updateBoardCell"]:
                await cursor.execute(
                    'SELECT MAX(sequence) FROM alerts WHERE action IN ("update", "updateBoardCell")'
                )
                last_seq = await cursor.fetchone()
                last_seq = last_seq[0]
                sequence = 1 if last_seq is None else last_seq + 1
            else:
                sequence = 0

            if message.get("target_sub_bridge") in [0, "0"]:
                await cursor.execute(
                    "DELETE FROM alerts WHERE cellId = ?",
                    (message.get("cellId"),)
                )
                logger.debug(f"Se borraron todos los registros para cellId {message.get('cellId')}.")
            await cursor.execute('''
                INSERT INTO alerts (cellId, mac_id, priority, program, plane, description, action, sequence, target_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(cellId, target_id) DO UPDATE SET
                    mac_id=excluded.mac_id,
                    priority=excluded.priority,
                    program=excluded.program,
                    plane=excluded.plane,
                    description=excluded.description,
                    action=excluded.action,
                    sequence=excluded.sequence,
                    target_id=excluded.target_id
            ''', (
                message.get("cellId"),
                message.get("mac_id"),
                message.get("priority"),
                message.get("program"),
                message.get("plane"),
                message.get("description"),
                action,
                sequence,
                message.get("target_sub_bridge", None)
            ))
            await conn.commit()
            logger.debug(f"Alerta '{message.get('cellId')}' con target_id {message.get('target_sub_bridge')} insertada/actualizada con sequence={sequence}.")
    except Exception as e:
        logger.exception(f"Error al insertar/actualizar alerta en SQLite: {e}")

async def load_all_alerts(db_file: str = DB_FILE):
    """
    Carga todas las alertas desde la base de datos sin filtrar por target.
    Retorna una tupla (resets, updates) en formato JSON.
    """
    try:
        async with aiosqlite.connect(db_file, timeout=30) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.cursor()
            await cursor.execute('SELECT * FROM alerts WHERE action = "reset" AND sequence = 0')
            reset_rows = await cursor.fetchall()
            await cursor.execute('SELECT * FROM alerts WHERE action = "updateBoardCell" ORDER BY sequence ASC')
            update_rows = await cursor.fetchall()

        resets = [json.dumps({
            "cellId": row["cellId"],
            "mac_id": row["mac_id"],
            "priority": row["priority"],
            "program": row["program"],
            "plane": row["plane"],
            "description": row["description"],
            "action": row["action"],
            "sequence": row["sequence"],
            "target_id": row["target_id"]
        }) for row in reset_rows]

        updates = [json.dumps({
            "cellId": row["cellId"],
            "mac_id": row["mac_id"],
            "priority": row["priority"],
            "program": row["program"],
            "plane": row["plane"],
            "description": row["description"],
            "action": row["action"],
            "sequence": row["sequence"],
            "target_id": row["target_id"]
        }) for row in update_rows]

        logger.info(f"Cargado {len(resets)} resets y {len(updates)} updates desde la base de datos.")
        return resets, updates
    except Exception as e:
        logger.exception(f"Error cargando alertas desde SQLite: {e}")
        return [], []

async def load_alerts_for_subbridge(sub_bridge_id, db_file: str = DB_FILE):
    """
    Carga las alertas para un sub_bridge especfico.
    """
    try:
        async with aiosqlite.connect(db_file, timeout=30) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.cursor()
            await cursor.execute('''
                SELECT * FROM alerts
                WHERE action = "reset"
                  AND sequence = 0
                  AND (target_id = "0" OR target_id = ?)
            ''', (str(sub_bridge_id),))
            reset_rows = await cursor.fetchall()
            await cursor.execute('''
                SELECT * FROM alerts
                WHERE action = "updateBoardCell"
                  AND (target_id = "0" OR target_id = ?)
                ORDER BY sequence ASC
            ''', (str(sub_bridge_id),))
            update_rows = await cursor.fetchall()

        resets = [json.dumps({
            "cellId": row["cellId"],
            "mac_id": row["mac_id"],
            "priority": row["priority"],
            "program": row["program"],
            "plane": row["plane"],
            "description": row["description"],
            "action": row["action"],
            "sequence": row["sequence"],
            "target_id": row["target_id"]
        }) for row in reset_rows]

        updates = [json.dumps({
            "cellId": row["cellId"],
            "mac_id": row["mac_id"],
            "priority": row["priority"],
            "program": row["program"],
            "plane": row["plane"],
            "description": row["description"],
            "action": row["action"],
            "sequence": row["sequence"],
            "target_id": row["target_id"]
        }) for row in update_rows]

        logger.info(f"Cargado {len(resets)} resets y {len(updates)} updates para sub_bridge {sub_bridge_id}.")
        return resets, updates
    except Exception as e:
        logger.exception(f"Error cargando alertas para sub_bridge {sub_bridge_id}: {e}")
        return [], []

async def broadcast_message(message: str):
    """
    Envía 'message' a los sub_bridge correctos según el campo target_sub_bridge.
    Verifica el estado de la conexión antes de enviar.
    """
    try:
        data = json.loads(message)
    except Exception as e:
        logger.error(f"Error parseando el mensaje JSON: {e}")
        return

    target = data.get("target_sub_bridge", 0)
    recipients = []
    if target in [0, "0"]:
        recipients = list(sub_bridge_clients.values())
    else:
        target_list = str(target).split(",")
        target_list = [tid.strip() for tid in target_list if tid.strip()]
        for tid in target_list:
            if tid in sub_bridge_clients:
                recipients.append(sub_bridge_clients[tid])
            else:
                logger.warning(f"No se encontr un sub_bridge con id: {tid}")

    to_remove = set()
    for ws in recipients:
        retry_count = 3
        while retry_count > 0:
            try:
                # Verificar estado del WebSocket antes de enviar
                try:
                    pong_waiter = await ws.ping()
                    await asyncio.wait_for(pong_waiter, timeout=5)
                except Exception as e:
                    logger.error(f"WebSocket no responde para {ws.remote_address}: {e}")
                    retry_count -= 1
                    if retry_count > 0:
                        logger.warning(f"Reintentando envío ({retry_count} intentos restantes)")
                        await asyncio.sleep(1)
                        continue
                    to_remove.add(ws)
                    break

                await ws.send(message)
                logger.debug(f"Mensaje enviado a {ws.remote_address}: {message}")
                break
            except websockets.exceptions.ConnectionClosed as e:
                logger.error(f"Conexión cerrada al enviar mensaje a {ws.remote_address}: {e}")
                retry_count -= 1
                if retry_count > 0:
                    logger.warning(f"Reintentando envío ({retry_count} intentos restantes)")
                    await asyncio.sleep(1)
                    continue
                to_remove.add(ws)
                break
            except Exception as e:
                logger.error(f"Error enviando mensaje a {ws.remote_address}: {e}")
                retry_count -= 1
                if retry_count > 0:
                    logger.warning(f"Reintentando envío ({retry_count} intentos restantes)")
                    await asyncio.sleep(1)
                    continue
                to_remove.add(ws)
                break

    for ws in to_remove:
        for key, client in list(sub_bridge_clients.items()):
            if client == ws:
                del sub_bridge_clients[key]
                logger.info(f"Sub-bridge removido debido a error de envo: {ws.remote_address}")

async def send_next_media(websocket, sub_bridge_id, targetContainer, retry_count=3):
    """
    Envía el siguiente registro de media al cliente.
    """
    try:
        # Verificar que el WebSocket esté abierto y en el diccionario de clientes
        if sub_bridge_id not in sub_bridge_clients or sub_bridge_clients[sub_bridge_id] != websocket:
            logger.error(f"Sub-bridge {sub_bridge_id} no está registrado o el WebSocket no coincide")
            return

        try:
            pong_waiter = await websocket.ping()
            await asyncio.wait_for(pong_waiter, timeout=5)
        except Exception as e:
            logger.error(f"WebSocket no responde para sub_bridge {sub_bridge_id}: {e}")
            return

        # Cargar registros filtrados por target_id y targetContainer
        media = await load_all_media_by_container(sub_bridge_id, targetContainer)
        if not media:
            logger.warning(f"No se encontraron registros para enviar al sub_bridge {sub_bridge_id} en contenedor {targetContainer}.")
            return

        # Obtener índice persistente
        current_index = await get_media_index(sub_bridge_id, targetContainer)
        if current_index >= len(media):
            current_index = 0

        # Obtener y preparar el siguiente registro
        next_record = media[current_index]
        
        # Verificar formato del registro
        try:
            data = json.loads(next_record)
            if targetContainer == "videos-container":
                if not data.get("videoUrl"):
                    data["videoUrl"] = data.get("filename", "")
                data["action"] = "updateVideo"
                next_record = json.dumps(data)
            elif targetContainer == "photos-grid":
                data["action"] = "updatePicture"
                next_record = json.dumps(data)
            logger.debug(f"Registro formateado: {next_record}")
        except json.JSONDecodeError as e:
            logger.error(f"Error decodificando registro: {e}")
            return
        
        # Actualizar el índice de manera persistente usando módulo para asegurar el loop continuo
        await update_media_index(sub_bridge_id, targetContainer, (current_index + 1) % len(media))
        
        # Verificar estado de la conexión antes de enviar
        try:
            pong_waiter = await websocket.ping()
            await asyncio.wait_for(pong_waiter, timeout=5)
        except Exception as e:
            logger.error(f"WebSocket no responde para sub_bridge {sub_bridge_id}: {e}")
            if retry_count > 0:
                logger.warning(f"Reintentando envío ({retry_count} intentos restantes)")
                await asyncio.sleep(1)
                await send_next_media(websocket, sub_bridge_id, targetContainer, retry_count - 1)
            return

        try:
            await websocket.send(next_record)
            logger.info(f"Media enviado a sub_bridge {sub_bridge_id} en contenedor {targetContainer}: índice {current_index}")
        except websockets.exceptions.ConnectionClosed as e:
            logger.error(f"Conexión cerrada al enviar media a sub_bridge {sub_bridge_id}: {e}")
            if retry_count > 0:
                logger.warning(f"Reintentando envío de media ({retry_count} intentos restantes)")
                await asyncio.sleep(1)
                await send_next_media(websocket, sub_bridge_id, targetContainer, retry_count - 1)
        except Exception as e:
            logger.error(f"Error enviando media a sub_bridge {sub_bridge_id}: {e}")
            if retry_count > 0:
                logger.warning(f"Reintentando envío de media ({retry_count} intentos restantes)")
                await asyncio.sleep(1)
                await send_next_media(websocket, sub_bridge_id, targetContainer, retry_count - 1)
            
    except Exception as e:
        logger.error(f"Error en send_next_media para {sub_bridge_id} en {targetContainer}: {e}")
        if retry_count > 0:
            logger.warning(f"Reintentando envío de media ({retry_count} intentos restantes)")
            await asyncio.sleep(1)
            await send_next_media(websocket, sub_bridge_id, targetContainer, retry_count - 1)

async def handler(websocket):
    """
    Maneja las conexiones de clientes individuales.
    """
    connected_clients.add(websocket)
    logger.info(f"Nuevo cliente conectado: {websocket.remote_address}")

    sub_bridge_id = None
    try:
        # Esperar mensaje de identificación con timeout
        identification_message = await asyncio.wait_for(websocket.recv(), timeout=5)
        data = json.loads(identification_message)
        
        # Verificar identificación del sub_bridge
        if data.get("action") == "sub_bridge_identify" and "id" in data:
            sub_bridge_id = str(data["id"])
            sub_bridge_clients[sub_bridge_id] = websocket
            logger.info(f"Sub-bridge identificado: ID {sub_bridge_id} conectado desde {websocket.remote_address}")
            
            # Asegurar que el WebSocket sigue abierto después de la identificación
            try:
                pong_waiter = await websocket.ping()
                await asyncio.wait_for(pong_waiter, timeout=5)
            except Exception as e:
                logger.error(f"WebSocket no responde después de identificación para sub_bridge {sub_bridge_id}: {e}")
                return
        else:
            logger.info("Cliente no se identificó como sub_bridge.")
            return
    except asyncio.TimeoutError:
        logger.info("No se recibió mensaje de identificación. El cliente podría no ser un sub_bridge.")
        return
    except Exception as e:
        logger.error(f"Error procesando el mensaje de identificación: {e}")
        return

    try:
        # Cargar y enviar alertas solo para sub_bridges identificados
        if sub_bridge_id is not None:
            # Verificar que el WebSocket sigue abierto
            try:
                pong_waiter = await websocket.ping()
                await asyncio.wait_for(pong_waiter, timeout=5)
                logger.info(f"WebSocket activo para sub_bridge {sub_bridge_id} - Preparando envío de alertas")
            except Exception as e:
                logger.error(f"WebSocket no responde antes de enviar alertas para sub_bridge {sub_bridge_id}: {e}")
                return

            # Cargar y enviar alertas
            resets, updates = await load_alerts_for_subbridge(sub_bridge_id)
            retry_count = 3
            for reset in resets:
                while retry_count > 0:
                    try:
                        await websocket.send(reset)
                        logger.debug(f"Reset enviado a {websocket.remote_address}: {reset}")
                        break
                    except websockets.exceptions.ConnectionClosed as e:
                        logger.error(f"Conexión cerrada al enviar reset a {websocket.remote_address}: {e}")
                        retry_count -= 1
                        if retry_count > 0:
                            logger.warning(f"Reintentando envío de reset ({retry_count} intentos restantes)")
                            await asyncio.sleep(1)
                            continue
                        return
                    except Exception as e:
                        logger.error(f"Error enviando reset a {websocket.remote_address}: {e}")
                        retry_count -= 1
                        if retry_count > 0:
                            logger.warning(f"Reintentando envío de reset ({retry_count} intentos restantes)")
                            await asyncio.sleep(1)
                            continue
                        return

            retry_count = 3
            for update in updates:
                while retry_count > 0:
                    try:
                        await websocket.send(update)
                        logger.debug(f"Update enviado a {websocket.remote_address}: {update}")
                        await asyncio.sleep(0.2)
                        break
                    except websockets.exceptions.ConnectionClosed as e:
                        logger.error(f"Conexión cerrada al enviar update a {websocket.remote_address}: {e}")
                        retry_count -= 1
                        if retry_count > 0:
                            logger.warning(f"Reintentando envío de update ({retry_count} intentos restantes)")
                            await asyncio.sleep(1)
                            continue
                        return
                    except Exception as e:
                        logger.error(f"Error enviando update a {websocket.remote_address}: {e}")
                        retry_count -= 1
                        if retry_count > 0:
                            logger.warning(f"Reintentando envío de update ({retry_count} intentos restantes)")
                            await asyncio.sleep(1)
                            continue
                        return

            # Verificar conexión antes de enviar media
            try:
                pong_waiter = await websocket.ping()
                await asyncio.wait_for(pong_waiter, timeout=5)
                logger.info(f"WebSocket activo para sub_bridge {sub_bridge_id} - Preparando envío de media")
                if sub_bridge_id in sub_bridge_clients:
                    # Send videos first since that's where the data is
                    logger.info(f"Iniciando envío de videos para sub_bridge {sub_bridge_id}")
                    await send_next_media(websocket, sub_bridge_id, "videos-container")
                    await asyncio.sleep(1)  # Increased delay between sends
                    logger.info(f"Iniciando envío de fotos para sub_bridge {sub_bridge_id}")
                    await send_next_media(websocket, sub_bridge_id, "photos-grid")
                    logger.info(f"Media inicial enviado exitosamente para sub_bridge {sub_bridge_id}")
            except Exception as e:
                logger.error(f"WebSocket no responde o sub_bridge {sub_bridge_id} no registrado antes de enviar media: {e}")
                logger.debug(f"Estado de conexión para sub_bridge {sub_bridge_id}: {'registrado' if sub_bridge_id in sub_bridge_clients else 'no registrado'}")
        # Procesar mensajes entrantes
        async for data in websocket:
            logger.info(f"Mensaje recibido de {websocket.remote_address}: {data}")
            try:
                # Verificar estado del WebSocket antes de procesar mensaje
                try:
                    pong_waiter = await websocket.ping()
                    await asyncio.wait_for(pong_waiter, timeout=5)
                except Exception as e:
                    logger.error(f"WebSocket no responde durante procesamiento de mensaje para sub_bridge {sub_bridge_id}: {e}")
                    return

                parsed = json.loads(data)
                action = parsed.get("action")
                
                if action == "effectCompleted":
                    logger.info("Efecto completado; enviando siguiente registro.")
                    targetContainer = parsed.get("targetContainer", "photos-grid")
                    if sub_bridge_id is not None and sub_bridge_id in sub_bridge_clients:
                        await send_next_media(websocket, sub_bridge_id, targetContainer)
                    else:
                        logger.error(f"Sub-bridge {sub_bridge_id} no registrado para enviar siguiente media")
                elif action in ["update", "updateBoardCell", "reset"]:
                    await upsert_alert(parsed)
                elif action in ["insertPicture", "insertVideo"]:
                    await insert_media_if_not_exists(parsed)
                elif action in ["updatePicture", "updateVideo"]:
                    await update_media(parsed)
                elif action in ["deletePicture", "deleteVideo"]:
                    await delete_media(parsed)

                if "target_sub_bridge" in parsed:
                    await broadcast_message(data)
            except Exception as e:
                logger.error(f"Error procesando mensaje de {websocket.remote_address}: {e}")
                return

    finally:
        # Cleanup connected clients
        if websocket in connected_clients:
            connected_clients.remove(websocket)
            logger.info(f"Cliente removido: {websocket.remote_address}")

        # Cleanup sub_bridge clients
        for key, ws in list(sub_bridge_clients.items()):
            if ws == websocket:
                del sub_bridge_clients[key]
                logger.info(f"Sub-bridge con ID {key} removido.")
                # Ensure we log any pending media state
                try:
                    current_index = await get_media_index(key, "videos-container")
                    logger.info(f"Estado final de media para sub_bridge {key}: índice {current_index}")
                except Exception as e:
                    logger.error(f"Error obteniendo estado final de media para sub_bridge {key}: {e}")

async def main():
    """
    Funcin principal para iniciar el servidor WebSocket.
    """
    await init_db()
    try:
        server = await websockets.serve(
            handler,
            "0.0.0.0",
            6789,
            ping_interval=20,
            ping_timeout=20
        )
        logger.info("Servidor WebSocket escuchando en ws://0.0.0.0:6789")
        await server.wait_closed()
    except Exception as e:
        logger.critical(f"Error al iniciar el servidor WebSocket: {e}", exc_info=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Servidor detenido manualmente por el usuario.")
    except Exception as e:
        logger.critical(f"Error crtico en el servidor: {e}", exc_info=True)
