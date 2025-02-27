// websocket_client.js

// Función para obtener la dirección MAC del servidor
function getMacAddress(siteId) {
    return fetch(`get_mac_address.php?site_id=${siteId}`)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok');
            }
            return response.json();
        })
        .then(data => {
            if (data.error) {
                console.error('Error getting MAC address:', data.error);
                showMessage(`Error getting MAC address: ${data.error}`, 'error');
                return null;
            }
            console.log('MAC address retrieved:', data.mac_address);
            return data.mac_address;
        })
        .catch(error => {
            console.error('Error fetching MAC address:', error);
            showMessage('Error fetching MAC address', 'error');
            return null;
        });
}

// Función para enviar un mensaje JSON al servidor websocket
function sendWebsocketMessage(cellId, macId, action = "updateBoardCell") {
    // Seleccionar un efecto aleatorio
    const effects = ["flipInY", "bounceIn", "zoomInLeft", "zoomInRight", "jackInTheBox"];
    const randomEffect = effects[Math.floor(Math.random() * effects.length)];
    
    // Construir el mensaje JSON
    const message = {
        "mac_id": macId,
        "priority": "normal",
        "program": "bridge_server.py",
        "plane": 2,
        "description": action === "reset" ? "reset cell image" : "update board cell",
        "cellId": cellId,
        "action": action,
        "effect": randomEffect,
        "target_sub_bridge": 0,
        "duration": 2,
        "delay": 0,
        "iterationCount": 3,
        "keepFinalState": true,
        "requires_confirmation": true
    };
    
    // Enviar el mensaje al servidor TCP
    fetch('send_websocket_message.php', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(message)
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(data => {
        if (data.error) {
            console.error('Error sending message:', data.error);
            showMessage(`Error sending message: ${data.error}`, 'error');
        } else {
            console.log('Message sent successfully:', data);
            showMessage(`Message sent for ${cellId} (${action})`, 'success');
        }
    })
    .catch(error => {
        console.error('Error sending message:', error);
        showMessage('Error sending message to server', 'error');
    });
}

/**
 * Función para enviar un mensaje de texto JSON al servidor websocket
 * @param {string} text - El texto a enviar
 * @param {string} macId - La dirección MAC del cliente
 * @param {string} fontFamily - La familia de fuente (opcional)
 * @param {string} fontSize - El tamaño de fuente (opcional)
 * @param {string} color - El color del texto (opcional)
 * @param {string} effect - El efecto a aplicar (opcional)
 * @param {number} duration - La duración del efecto en segundos (opcional)
 * @param {number} delay - El retraso antes de mostrar el texto en segundos (opcional)
 */
function sendTextMessage(text, macId, fontFamily = "Courier New", fontSize = "100px", color = "#FFFFFF", effect = null, duration = 2, delay = 0) {
    // Seleccionar un efecto aleatorio si no se proporciona
    if (!effect) {
        const effects = ["flipInY", "bounceIn", "zoomInLeft", "zoomInRight", "jackInTheBox"];
        effect = effects[Math.floor(Math.random() * effects.length)];
    }
    
    // Construir el mensaje JSON exactamente como en el script Python de ejemplo
    const message = {
        "mac_id": macId,
        "priority": "normal",
        "program": "bridge_server.py",
        "plane": 2,
        "description": "update text",
        "action": "updateText",
        "text": text,
        "fontFamily": fontFamily,
        "fontSize": fontSize,
        "color": color,
        "effect": effect,
        "duration": duration,
        "delay": delay,
        "target_sub_bridge": 0
    };
    
    // Enviar el mensaje al servidor TCP
    fetch('send_websocket_message.php', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(message)
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(data => {
        if (data.error) {
            console.error('Error sending text message:', data.error);
            showMessage(`Error sending text message: ${data.error}`, 'error');
        } else {
            console.log('Text message sent successfully:', data);
            showMessage(`Text message sent: "${text}"`, 'success');
        }
    })
    .catch(error => {
        console.error('Error sending text message:', error);
        showMessage('Error sending text message to server', 'error');
    });
}

// Función para generar todos los cell_ids posibles
function generateAllCellIds() {
    const allCells = [];
    
    // B = 1 a 15
    for (let i = 1; i <= 15; i++) {
        allCells.push(`B${i}`);
    }
    // I = 16 a 30
    for (let i = 16; i <= 30; i++) {
        allCells.push(`I${i}`);
    }
    // N = 31 a 45
    for (let i = 31; i <= 45; i++) {
        allCells.push(`N${i}`);
    }
    // G = 46 a 60
    for (let i = 46; i <= 60; i++) {
        allCells.push(`G${i}`);
    }
    // O = 61 a 75
    for (let i = 61; i <= 75; i++) {
        allCells.push(`O${i}`);
    }
    
    return allCells;
}

// Función para enviar mensajes de reset para todos los números
function sendResetAllMessages(macId) {
    if (!macId) {
        console.error("MAC address is required to send reset messages");
        showMessage("Error: MAC address is required to send reset messages", "error");
        return;
    }
    
    const allCells = generateAllCellIds();
    console.log(`Sending reset messages for ${allCells.length} cells`);
    
    // Enviar mensajes de reset para cada celda
    allCells.forEach((cellId, index) => {
        // Añadir un pequeño retraso para evitar sobrecargar el servidor
        setTimeout(() => {
            sendWebsocketMessage(cellId, macId, "reset");
        }, index * 20); // 20ms de retraso entre mensajes
    });
}
