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
