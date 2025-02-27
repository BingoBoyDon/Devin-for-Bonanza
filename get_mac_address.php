<?php
// get_mac_address.php

header('Content-Type: application/json');

// Incluir el autoloader de Composer
require_once '/var/www/weblynxx/vendor/autoload.php';

// Cargar las variables de entorno
$dotenv = Dotenv\Dotenv::createImmutable('/var/www/weblynxx', 'db_credentials.env');
$dotenv->load();

// Obtener las credenciales de la base de datos
$dbHost = $_ENV['DB_HOST'];
$dbName = $_ENV['DB_NAME'];
$dbUser = $_ENV['DB_USER'];
$dbPass = $_ENV['DB_PASS'];

// Validar el parámetro site_id
if (!isset($_GET['site_id']) || empty($_GET['site_id'])) {
    echo json_encode(["error" => "Site ID is required"]);
    exit;
}

$siteId = intval($_GET['site_id']);

if ($siteId <= 0) {
    echo json_encode(["error" => "Invalid Site ID"]);
    exit;
}

// Establecer la conexión con la base de datos
$connectionString = "host=$dbHost dbname=$dbName user=$dbUser password=$dbPass";
$dbconn = pg_connect($connectionString);

if (!$dbconn) {
    echo json_encode(["error" => "Database connection error"]);
    exit;
}

// Consultar la dirección MAC para el site_id dado
$query = "SELECT mac_address FROM subscribers WHERE ip_site_id = $1";
$result = pg_query_params($dbconn, $query, array($siteId));

if (!$result) {
    echo json_encode(["error" => "Query error: " . pg_last_error()]);
    pg_close($dbconn);
    exit;
}

if (pg_num_rows($result) === 0) {
    echo json_encode(["error" => "No MAC address found for the given Site ID"]);
    pg_close($dbconn);
    exit;
}

$row = pg_fetch_assoc($result);
$macAddress = $row['mac_address'];

// Devolver la dirección MAC
echo json_encode(["mac_address" => $macAddress]);

pg_close($dbconn);
?>
