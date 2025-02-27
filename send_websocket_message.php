<?php
// send_websocket_message.php

header('Content-Type: application/json');

// Obtener el cuerpo de la solicitud
$data = json_decode(file_get_contents('php://input'), true);

// Validar los datos entrantes
if (!isset($data['mac_id'])) {
    echo json_encode(["error" => "Invalid data: mac_id is required"]);
    exit;
}

// Validar según el tipo de acción
if (isset($data['action'])) {
    // Para mensajes de texto (action = updateText)
    if ($data['action'] === 'updateText' && !isset($data['text'])) {
        echo json_encode(["error" => "Invalid data: text is required for updateText action"]);
        exit;
    }
    // Para actualización de celdas (action = updateBoardCell o reset)
    else if (($data['action'] === 'updateBoardCell' || $data['action'] === 'reset') && !isset($data['cellId'])) {
        echo json_encode(["error" => "Invalid data: cellId is required for updateBoardCell or reset action"]);
        exit;
    }
} else {
    echo json_encode(["error" => "Invalid data: action is required"]);
    exit;
}

// Configuración del servidor TCP
$host = "147.182.253.126";
$port = 9999;

// Crear un socket TCP/IP
$socket = socket_create(AF_INET, SOCK_STREAM, SOL_TCP);
if ($socket === false) {
    echo json_encode(["error" => "Socket creation failed: " . socket_strerror(socket_last_error())]);
    exit;
}

// Conectar al servidor
$result = socket_connect($socket, $host, $port);
if ($result === false) {
    echo json_encode(["error" => "Connection failed: " . socket_strerror(socket_last_error($socket))]);
    socket_close($socket);
    exit;
}

// Convertir el array a JSON
$jsonData = json_encode($data);

// Enviar el mensaje
socket_write($socket, $jsonData, strlen($jsonData));

// Cerrar el socket
socket_close($socket);

// Devolver respuesta exitosa
echo json_encode(["success" => true, "message" => "Message sent successfully"]);
?>
