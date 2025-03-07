#!/usr/bin/python3

import os
import sys
import json
import logging
import psycopg2
from datetime import datetime

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[
        logging.FileHandler("/var/log/bonanza/balance_db_updater.log"),
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

def update_balance_adjustment(adjustment_id, previous_balance, new_balance, transaction_id):
    """
    Actualiza los campos balance, previous_balance y transaction_id en la tabla balance_adjustments.
    
    Args:
        adjustment_id (int): ID del ajuste en la tabla balance_adjustments
        previous_balance (int): Balance inicial antes del ajuste
        new_balance (int): Nuevo balance después del ajuste
        transaction_id (int): ID de la transacción generada por el sistema
    
    Returns:
        bool: True si la actualización fue exitosa, False en caso contrario
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE balance_adjustments
            SET waiting_processes = FALSE, 
                balance = %s, 
                previous_balance = %s, 
                transaction_id = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (new_balance, previous_balance, transaction_id, adjustment_id))
        
        rows_updated = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        
        if rows_updated == 0:
            logger.warning(f"No se encontró ningún registro con adjustment_id={adjustment_id}")
            return False
        else:
            logger.info(f"Actualización exitosa para adjustment_id={adjustment_id}, previous_balance={previous_balance}, new_balance={new_balance}, transaction_id={transaction_id}")
            return True
    except Exception as e:
        logger.error(f"Error actualizando balance_adjustments: {e}")
        return False

def client_exists_in_db(mac_address):
    """
    Verifica si un cliente existe en la base de datos.
    
    Args:
        mac_address (str): Dirección MAC del cliente
    
    Returns:
        bool: True si el cliente existe, False en caso contrario
    """
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

def insert_or_update_client_in_db(client_id, public_ip, mac_address):
    """
    Inserta o actualiza un cliente en la base de datos.
    
    Args:
        client_id (str): ID del cliente
        public_ip (str): IP pública del cliente
        mac_address (str): Dirección MAC del cliente
    
    Returns:
        bool: True si la operación fue exitosa, False en caso contrario
    """
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
                SET public_ip = %s, status = 'online', updated_at = CURRENT_TIMESTAMP
                WHERE mac_address = %s
            """, (public_ip, mac_address))
        else:
            # Insertar nuevo cliente
            cursor.execute("""
                INSERT INTO clients (client_id, public_ip, mac_address, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'online', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """, (client_id, public_ip, mac_address))
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error inserting/updating client in DB: {e}")
        return False

def update_client_status(mac_address, status):
    """
    Actualiza el estado del cliente en la base de datos.
    
    Args:
        mac_address (str): Dirección MAC del cliente
        status (str): Nuevo estado del cliente
    
    Returns:
        bool: True si la actualización fue exitosa, False en caso contrario
    """
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
        return True
    except Exception as e:
        logger.error(f"Error updating client status in DB: {e}")
        return False

def update_processor_response_time(client_id, draw_id, response_time):
    """
    Actualiza el tiempo de respuesta del procesador.
    
    Args:
        client_id (str): ID del cliente
        draw_id (int): ID del sorteo
        response_time (float): Tiempo de respuesta en segundos
    
    Returns:
        bool: True si la actualización fue exitosa, False en caso contrario
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Buscar el ID del cliente por su MAC
        cursor.execute("SELECT id FROM clients WHERE mac_address = %s", (client_id,))
        client_result = cursor.fetchone()
        
        if not client_result:
            logger.error(f"Client {client_id} not found in database")
            cursor.close()
            conn.close()
            return False
        
        client_db_id = client_result[0]
        
        # Insertar el tiempo de respuesta
        cursor.execute("""
            INSERT INTO processor_response_times (client_id, draw_id, response_time, created_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
        """, (client_db_id, draw_id, response_time))
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error updating processor response time in DB: {e}")
        return False

def get_pending_commands():
    """
    Obtiene los comandos pendientes de la base de datos.
    
    Returns:
        list: Lista de diccionarios con los comandos pendientes (id, command_code, created_at, mac_address)
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Buscar comandos que no han sido enviados
        cursor.execute("""
            SELECT c.id, c.command_code, c.created_at, cl.mac_address
            FROM commands c
            JOIN clients cl ON c.client_id = cl.id
            WHERE c.sent = FALSE
            ORDER BY c.created_at ASC
        """)
        
        results = cursor.fetchall()
        cursor.close()
        conn.close()
        
        commands = []
        for result in results:
            commands.append({
                "id": result[0],
                "command_code": result[1],
                "created_at": result[2].strftime("%Y-%m-%d %H:%M:%S"),
                "mac_address": result[3]
            })
        
        return commands
    except Exception as e:
        logger.error(f"Error getting pending commands from DB: {e}")
        return []

def update_command_status(command_id, sent=True):
    """
    Actualiza el estado de un comando en la base de datos.
    
    Args:
        command_id (int): ID del comando
        sent (bool): Indica si el comando fue enviado
    
    Returns:
        bool: True si la actualización fue exitosa, False en caso contrario
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE commands
            SET sent = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        """, (sent, command_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error updating command status in DB: {e}")
        return False

def get_pending_adjustments(client_id):
    """
    Consulta los ajustes de balance pendientes para un cliente específico.
    
    Args:
        client_id (str): MAC address del cliente
    
    Returns:
        list: Lista de diccionarios con los ajustes pendientes (id, costumers_id, amount, phone_number)
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT ba.id, ba.costumers_id, ba.amount, c.phone_number
            FROM balance_adjustments ba
            JOIN costumers c ON ba.costumers_id = c.id
            JOIN clients cl ON c.client_id = cl.id
            WHERE cl.mac_address = %s AND ba.waiting_processes = TRUE
            LIMIT 1
        """, (client_id,))
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            return [{"id": result[0], "costumers_id": result[1], "amount": result[2], "phone_number": result[3]}]
        else:
            return []
    except Exception as e:
        logger.error(f"Error consultando ajustes pendientes: {e}")
        return []

def main():
    """
    Función principal que lee los datos de entrada y realiza la operación correspondiente.
    Espera un JSON con los campos necesarios según la operación:
    - Para actualizar balance: adjustment_id, previous_balance, new_balance, transaction_id
    - Para consultar ajustes pendientes: client_id, command="get_pending"
    - Para verificar si un cliente existe: mac_address, command="client_exists"
    - Para insertar o actualizar un cliente: client_id, public_ip, mac_address, command="insert_or_update_client"
    - Para actualizar el estado de un cliente: mac_address, status, command="update_client_status"
    - Para actualizar el tiempo de respuesta: client_id, draw_id, response_time, command="update_response_time"
    - Para obtener comandos pendientes: command="get_pending_commands"
    - Para actualizar el estado de un comando: command_id, sent, command="update_command_status"
    """
    try:
        # Leer datos de entrada (JSON)
        input_data = sys.stdin.read().strip()
        data = json.loads(input_data)
        
        # Determinar la operación a realizar
        command = data.get('command', 'update')
        
        if command == 'get_pending':
            # Consultar ajustes pendientes
            client_id = data.get('client_id')
            if not client_id:
                print(json.dumps({"success": False, "error": "Client ID is required"}))
                return
            
            adjustments = get_pending_adjustments(client_id)
            print(json.dumps({"success": True, "adjustments": adjustments}))
        
        elif command == 'client_exists':
            # Verificar si un cliente existe
            mac_address = data.get('mac_address')
            if not mac_address:
                print(json.dumps({"success": False, "error": "MAC address is required"}))
                return
            
            exists = client_exists_in_db(mac_address)
            print(json.dumps({"success": True, "exists": exists}))
        
        elif command == 'insert_or_update_client':
            # Insertar o actualizar un cliente
            client_id = data.get('client_id')
            public_ip = data.get('public_ip')
            mac_address = data.get('mac_address')
            
            if not all([client_id, public_ip, mac_address]):
                print(json.dumps({"success": False, "error": "Client ID, public IP, and MAC address are required"}))
                return
            
            success = insert_or_update_client_in_db(client_id, public_ip, mac_address)
            print(json.dumps({"success": success}))
        
        elif command == 'update_client_status':
            # Actualizar el estado de un cliente
            mac_address = data.get('mac_address')
            status = data.get('status')
            
            if not all([mac_address, status]):
                print(json.dumps({"success": False, "error": "MAC address and status are required"}))
                return
            
            success = update_client_status(mac_address, status)
            print(json.dumps({"success": success}))
        
        elif command == 'update_response_time':
            # Actualizar el tiempo de respuesta
            client_id = data.get('client_id')
            draw_id = data.get('draw_id')
            response_time = data.get('response_time')
            
            if not all([client_id, draw_id, response_time]):
                print(json.dumps({"success": False, "error": "Client ID, draw ID, and response time are required"}))
                return
            
            success = update_processor_response_time(client_id, draw_id, response_time)
            print(json.dumps({"success": success}))
        
        elif command == 'get_pending_commands':
            # Obtener comandos pendientes
            commands = get_pending_commands()
            print(json.dumps({"success": True, "commands": commands}))
        
        elif command == 'update_command_status':
            # Actualizar el estado de un comando
            command_id = data.get('command_id')
            sent = data.get('sent', True)
            
            if command_id is None:
                print(json.dumps({"success": False, "error": "Command ID is required"}))
                return
            
            success = update_command_status(command_id, sent)
            print(json.dumps({"success": success}))
        
        else:
            # Actualizar balance (comportamiento original)
            adjustment_id = data.get('adjustment_id')
            previous_balance = data.get('previous_balance')
            new_balance = data.get('new_balance')
            transaction_id = data.get('transaction_id', 0)
            
            # Actualizar la base de datos
            success = update_balance_adjustment(adjustment_id, previous_balance, new_balance, transaction_id)
            
            # Devolver resultado
            print(json.dumps({"success": success}))
    except Exception as e:
        logger.error(f"Error en el procesamiento de datos: {e}")
        print(json.dumps({"success": False, "error": str(e)}))

if __name__ == "__main__":
    main()
