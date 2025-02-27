// websocket_client.js

// Variable global para almacenar la dirección MAC

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
function sendWebsocketMessage(cellId, macId) {
    // Seleccionar un efecto aleatorio
    const effects = ["flipInY", "bounceIn", "zoomInLeft", "zoomInRight", "jackInTheBox"];
    const randomEffect = effects[Math.floor(Math.random() * effects.length)];
    
    // Construir el mensaje JSON
    const message = {
        mac_id: macId,
        priority: "normal",
        program: "bridge_server.py",
        plane: 2,
        description: "update board cell",
        cellId: cellId,
        action: "updateBoardCell",
        effect: randomEffect,
        target_sub_bridge: 0,
        duration: 2,
        delay: 0,
        iterationCount: 3,
        keepFinalState: true,
        requires_confirmation: true
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
            showMessage(`Message sent for ${cellId}`, 'success');
        }
    })
    .catch(error => {
        console.error('Error sending message:', error);
        showMessage('Error sending message to server', 'error');
    });
}
