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
