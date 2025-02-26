#!/usr/bin/env python3
__version__ = '1.3.10'
import asyncio
import websockets
import json
import aiosqlite
import os
import logging
from logging.handlers import RotatingFileHandler

from media_handler import (
    init_media_db,
    insert_media_if_not_exists,
    update_media,
    delete_media,
    load_all_media,
    load_all_media_by_container
)

logger = logging.getLogger("BridgeServer")
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('[%(asctime)s] %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
log_file = "bridge_server.log"
handler = RotatingFileHandler(log_file, maxBytes=5*1024*1024, backupCount=5)
handler.setLevel(logging.DEBUG)
handler.setFormatter(formatter)
logger.addHandler(handler)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

DB_FILE = "bridge_server.db"
connected_clients = set()
sub_bridge_clients = {}
media_indices = {}

async def init_db(db_file: str = DB_FILE):
    async with aiosqlite.connect(db_file, timeout=30) as conn:
        await conn.execute("PRAGMA journal_mode=WAL;")
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
        await conn.commit()
    await init_media_db(db_file)
    logger.info("Base de datos SQLite inicializada correctamente.")

async def upsert_alert(message: dict, db_file: str = DB_FILE):
    try:
        async with aiosqlite.connect(db_file, timeout=30) as conn:
            cursor = await conn.cursor()
            action = message.get("action")
            if action == "reset":
                sequence = 0
            elif action in ["update", "updateBoardCell"]:
                await cursor.execute('SELECT MAX(sequence) FROM alerts WHERE action IN ("update", "updateBoardCell")')
                last_seq = await cursor.fetchone()
                sequence = 1 if last_seq[0] is None else last_seq[0] + 1
            else:
                sequence = 0

            if message.get("target_sub_bridge") in [0, "0"]:
                await cursor.execute("DELETE FROM alerts WHERE cellId = ?", (message.get("cellId"),))
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
                message.get("cellId"), message.get("mac_id"), message.get("priority"), message.get("program"),
                message.get("plane"), message.get("description"), action, sequence, message.get("target_sub_bridge", None)
            ))
            await conn.commit()
            logger.info(f"Alerta guardada en base de datos: {message.get('cellId')}")
    except Exception as e:
        logger.error(f"Error al guardar alerta en base de datos: {e}")
        raise  # Re-lanzar la excepción para que se maneje en el handler

async def load_all_alerts(db_file: str = DB_FILE):
    async with aiosqlite.connect(db_file, timeout=30) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.cursor()
        await cursor.execute('SELECT * FROM alerts WHERE action = "reset" AND sequence = 0')
        reset_rows = await cursor.fetchall()
        await cursor.execute('SELECT * FROM alerts WHERE action = "updateBoardCell" ORDER BY sequence ASC')
        update_rows = await cursor.fetchall()

    resets = [json.dumps(dict(row)) for row in reset_rows]
    updates = [json.dumps(dict(row)) for row in update_rows]
    return resets, updates

async def load_alerts_for_subbridge(sub_bridge_id, db_file: str = DB_FILE):
    async with aiosqlite.connect(db_file, timeout=30) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.cursor()
        await cursor.execute('''
            SELECT * FROM alerts WHERE action = "reset" AND sequence = 0 AND (target_id = "0" OR target_id = ?)
        ''', (str(sub_bridge_id),))
        reset_rows = await cursor.fetchall()
        await cursor.execute('''
            SELECT * FROM alerts WHERE action = "updateBoardCell" AND (target_id = "0" OR target_id = ?) ORDER BY sequence ASC
        ''', (str(sub_bridge_id),))
        update_rows = await cursor.fetchall()

    resets = [json.dumps(dict(row)) for row in reset_rows]
    updates = [json.dumps(dict(row)) for row in update_rows]
    return resets, updates

async def broadcast_message(message: str):
    data = json.loads(message)
    target = data.get("target_sub_bridge", 0)
    recipients = []
    if target in [0, "0"]:
        recipients = list(sub_bridge_clients.values())
    else:
        target_list = str(target).split(",")
        target_list = [tid.strip() for tid in target_list if tid.strip()]
        recipients = [sub_bridge_clients[tid] for tid in target_list if tid in sub_bridge_clients]

    to_remove = set()
    for ws in recipients:
        try:
            await ws.send(message)
        except Exception:
            to_remove.add(ws)

    for ws in to_remove:
        for key, client in list(sub_bridge_clients.items()):
            if client == ws:
                del sub_bridge_clients[key]

async def send_next_media(websocket, sub_bridge_id, targetContainer):
    global media_indices
    media = await load_all_media_by_container(sub_bridge_id, targetContainer)
    if not media:
        return
    key = f"{sub_bridge_id}_{targetContainer}"
    current_index = media_indices.get(key, 0)
    if current_index >= len(media):
        current_index = 0
    next_record = media[current_index]
    media_indices[key] = current_index + 1
    await websocket.send(next_record)

async def send_confirmation(websocket, message_id):
    """
    Envía una confirmación al cliente para un mensaje específico.
    Solo se debe llamar después de operaciones exitosas en la base de datos.
    """
    if message_id:
        confirmation = {"confirmation": "processed", "id": message_id}
        await websocket.send(json.dumps(confirmation))
        logger.info(f"Confirmación enviada: {confirmation}")

async def handler(websocket):
    connected_clients.add(websocket)
    logger.info(f"Nuevo cliente conectado: {websocket.remote_address}")
    sub_bridge_id = None

    try:
        identification_message = await asyncio.wait_for(websocket.recv(), timeout=5)
        data = json.loads(identification_message)
        if data.get("action") == "sub_bridge_identify" and "id" in data:
            sub_bridge_id = str(data["id"])
            sub_bridge_clients[sub_bridge_id] = websocket
            logger.info(f"Sub-bridge identificado: ID {sub_bridge_id}")
    except asyncio.TimeoutError:
        logger.info("No se recibió mensaje de identificación.")

    try:
        if sub_bridge_id is not None:
            resets, updates = await load_alerts_for_subbridge(sub_bridge_id)
        else:
            resets, updates = await load_all_alerts()
        for reset in resets:
            await websocket.send(reset)
        for update in updates:
            await websocket.send(update)
            await asyncio.sleep(0.2)

        if sub_bridge_id is not None:
            await send_next_media(websocket, sub_bridge_id, "photos-grid")
            await send_next_media(websocket, sub_bridge_id, "videos-container")
        else:
            await send_next_media(websocket, "0", "photos-grid")
            await send_next_media(websocket, "0", "videos-container")

        async for data in websocket:
            logger.info(f"Mensaje recibido: {data}")
            parsed = json.loads(data)
            message_id = parsed.get("id")
            action_data = parsed.get("data", parsed)
            action = action_data.get("action")
            
            # Flag para indicar si se requiere confirmación después de operación en BD
            requires_db_confirmation = False

            try:
                if action == "effectCompleted":
                    targetContainer = action_data.get("targetContainer", "photos-grid")
                    if sub_bridge_id is not None:
                        await send_next_media(websocket, sub_bridge_id, targetContainer)
                    else:
                        await send_next_media(websocket, "0", targetContainer)
                elif action in ["update", "updateBoardCell", "reset"]:
                    await upsert_alert(action_data)
                    requires_db_confirmation = True
                    logger.info(f"Operación de base de datos exitosa: {action}")
                elif action in ["insertPicture", "insertVideo"]:
                    await insert_media_if_not_exists(action_data)
                    requires_db_confirmation = True
                    logger.info(f"Operación de base de datos exitosa: {action}")
                elif action in ["updatePicture", "updateVideo"]:
                    await update_media(action_data)
                    requires_db_confirmation = True
                    logger.info(f"Operación de base de datos exitosa: {action}")
                elif action in ["deletePicture", "deleteVideo"]:
                    await delete_media(action_data)
                    requires_db_confirmation = True
                    logger.info(f"Operación de base de datos exitosa: {action}")

                if "target_sub_bridge" in action_data:
                    await broadcast_message(data)
                
                # Enviar confirmación solo si se requiere después de operación en BD
                if requires_db_confirmation and message_id:
                    await send_confirmation(websocket, message_id)
            except Exception as e:
                logger.error(f"Error en operación de base de datos: {e}")
                # No enviamos confirmación en caso de error

    finally:
        connected_clients.remove(websocket)
        for key, ws in list(sub_bridge_clients.items()):
            if ws == websocket:
                del sub_bridge_clients[key]
        logger.info(f"Cliente removido: {websocket.remote_address}")

async def main():
    await init_db()
    server = await websockets.serve(handler, "0.0.0.0", 6789, ping_interval=20, ping_timeout=20)
    logger.info("Servidor WebSocket escuchando en ws://0.0.0.0:6789")
    await server.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Servidor detenido manualmente.")
