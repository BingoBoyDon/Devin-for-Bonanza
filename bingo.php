
<?php
session_start();

// Establecer la duración del tiempo de espera de la sesión (en segundos)
$timeout_duration = 1000000; // 30 minutos

// Comprobar si se ha establecido la marca de tiempo de la última actividad
if (isset($_SESSION['LAST_ACTIVITY'])) {
    $elapsed_time = time() - $_SESSION['LAST_ACTIVITY'];
    if ($elapsed_time >= $timeout_duration) {
        // La sesión ha expirado
        session_unset();
        session_destroy();
        header("Location: /login/login.php");
        exit();
    }
    $time_remaining = $timeout_duration - $elapsed_time;
} else {
    $time_remaining = $timeout_duration;
}

// Actualizar la marca de tiempo de la última actividad
$_SESSION['LAST_ACTIVITY'] = time();

// Incluir el autoloader de Composer si es necesario
require_once '/var/www/weblynxx/vendor/autoload.php';

// Cargar las variables de entorno
$dotenv = Dotenv\Dotenv::createImmutable('/var/www/weblynxx', 'db_credentials.env');
$dotenv->load();

// Obtener las credenciales de la base de datos
$dbHost = $_ENV['DB_HOST'];
$dbName = $_ENV['DB_NAME'];
$dbUser = $_ENV['DB_USER'];
$dbPass = $_ENV['DB_PASS'];

// Establecer la conexión con la base de datos
$connectionString = "host=$dbHost dbname=$dbName user=$dbUser password=$dbPass";
$dbconn = pg_connect($connectionString);

if (!$dbconn) {
    error_log("Database connection error: " . pg_last_error());
    die("Error connecting to the database.");
}

// Obtener los valores desde la URL
$user_id = isset($_GET['user_id']) ? htmlspecialchars($_GET['user_id']) : null;
$site_id = isset($_GET['site_id']) ? htmlspecialchars($_GET['site_id']) : null;
$site_name = isset($_GET['site_name']) ? htmlspecialchars($_GET['site_name']) : null;

// Verificar los parámetros
if (!$user_id || !$site_id || !$site_name) {
    echo "<h1>Error: Missing or incorrect parameters.</h1>";
    exit;
}

// Registrar la acción en user_logs
if (isset($_SESSION['user_id'])) {
    $user_id = $_SESSION['user_id'];
    $action_type = 'BingoGameAccess'; // Tipo de acción
    $action_description = "Access to Master Board, site: $site_name"; // Descripción simplificada

    try {
        $pdo = new PDO("pgsql:host=$dbHost;dbname=$dbName", $dbUser, $dbPass);
        $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

        $logQuery = "INSERT INTO user_logs (user_id, action_type, action_description) VALUES (:user_id, :action_type, :action_description)";
        $logStmt = $pdo->prepare($logQuery);
        $logStmt->execute([
            'user_id' => $user_id,
            'action_type' => $action_type,
            'action_description' => $action_description
        ]);
    } catch (PDOException $e) {
        error_log("Error inserting into user_logs: " . $e->getMessage());
    }
}

// Realizar la consulta para obtener el valor de config
$query = "SELECT config FROM system_configuration
          WHERE site_id = $1 AND user_id = $2 AND active = true";
$result = pg_query_params($dbconn, $query, array($site_id, $user_id));

// Obtener el valor de config o establecer el predeterminado '0'
if ($result && pg_num_rows($result) > 0) {
    $config = pg_fetch_result($result, 0, 'config');
    error_log("Correct Config Value from DB: $config"); // Log para diagnóstico
} else {
    $config = '0'; // Valor predeterminado
    error_log("No valid configuration found. Defaulting to 0.");
}

// Verificar si se necesita realizar la consulta adicional
if ($config === '0') {
    $query_status = "SELECT on_schedule, special_schedule FROM schedule_status
                     WHERE site_id = $1";
    $result_status = pg_query_params($dbconn, $query_status, array($site_id));

    if ($result_status && pg_num_rows($result_status) > 0) {
        $row = pg_fetch_assoc($result_status);
        if ($row['on_schedule'] === 't' || $row['special_schedule'] === 't') {
            $config = '1';
        }
    }
}

// Cerrar la conexión a la base de datos
pg_close($dbconn);

// Pasar el valor de config y el tiempo restante de sesión a JavaScript
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <!-- ... [Tu contenido existente en el head] ... -->
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bingo Game</title>
    <link rel="stylesheet" href="style.css">
    <!-- Asegúrate de incluir tus estilos CSS aquí -->
    <link rel="stylesheet" href="style2.css">
    <link rel="stylesheet" href="style3.css">
</head>
<body>
    <header id="top-banner">
        <h2>Bingo Game # <span id="game-number"></span> | Site: <?php echo htmlspecialchars($site_name); ?></h2>
        <p><?php echo date('Y-m-d H:i:s'); ?></p>
    </header>

    <main id="main-container">
        <div id="bingo-container" class="sticky-header">
            <div class="column" id="B"><button class="column-header letter-b">B</button></div>
            <div class="column" id="I"><button class="column-header letter-i">I</button></div>
            <div class="column" id="N"><button class="column-header letter-n">N</button></div>
            <div class="column" id="G"><button class="column-header letter-g">G</button></div>
            <div class="column" id="O"><button class="column-header letter-o">O</button></div>
        </div>

        <section class="selected-numbers-container">
            <h1>Selected Numbers</h1>
            <div id="sequence-container"></div>
        </section>
    </main>

    <footer id="bottom-banner">
        <div class="buttons-container">
            <button id="go-back-button" class="go-back-button" onclick="goBack()">Go Back</button>
            <button id="reset-bingo-button">Reset Selected</button>
            <button id="set-bingo-button" style="display: none;" onclick="setBingo()">Set Bingo</button>
            <button id="previous-games-button" class="previous-games-button" onclick="showPreviousGamesModal()">Previous Games</button>
        </div>
    </footer>

    <div id="previous-games-modal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closePreviousGamesModal()">&times;</span>
            <form id="previous-games-form">
                <label for="game-date">Select Date:</label>
                <input type="date" id="game-date" name="game-date" required>
                <button type="button" onclick="loadPreviousGames()">Load Previous Games</button>
            </form>
            <div id="previous-games-list"></div>
        </div>
    </div>

    <div id="toast-container"></div>

    <!-- Spinner HTML añadido -->
    <div id="spinner-container" style="display: none;">
        <div class="spinner"></div>
        <div id="spinner-message"></div>
    </div>

    <!-- Modal de advertencia de expiración de sesión -->
    <div id="session-expiry-modal" style="display: none;">
        <div class="modal-content">
            <p>Your session is about to expire. Do you want to continue?</p>
            <p id="session-countdown">Time remaining: 60 seconds</p>
            <button id="session-continue-button">Yes</button>
        </div>
    </div>

    <script>
        const configValue = <?php echo json_encode($config); ?>;
        const timeRemaining = <?php echo $time_remaining; ?>;
        console.log("Config Value passed to JS:", configValue);
        console.log("Time Remaining:", timeRemaining);

        function goBack() {
            window.history.back();
        }

        // Manejo de la expiración de sesión en JavaScript
        (function() {
            const timeoutDuration = <?php echo $timeout_duration; ?>;
            const warningTime = timeRemaining - 60; // Mostrar advertencia 1 minuto antes

            if (warningTime > 0) {
                setTimeout(showSessionExpiryWarning, warningTime * 1000);
            } else if (timeRemaining > 0) {
                // Si el tiempo restante es menor o igual a 60 segundos, mostrar inmediatamente la advertencia
                setTimeout(showSessionExpiryWarning, 0);
            }

            function showSessionExpiryWarning() {
                const modal = document.getElementById('session-expiry-modal');
                modal.style.display = 'block';

                let timeLeft = Math.min(timeRemaining, 60); // segundos
                const countdownElement = document.getElementById('session-countdown');
                const interval = setInterval(function() {
                    countdownElement.textContent = 'Time remaining: ' + timeLeft + ' seconds';
                    timeLeft--;
                    if (timeLeft < 0) {
                        clearInterval(interval);
                        window.location.href = '/login/login.php';
                    }
                }, 1000);

                document.getElementById('session-continue-button').onclick = function() {
                    // Enviar solicitud AJAX para reiniciar el temporizador de la sesión
                    resetSessionTimer();
                    // Ocultar el modal
                    modal.style.display = 'none';
                    // Limpiar el intervalo
                    clearInterval(interval);
                    // Reiniciar el temporizador de advertencia
                    setTimeout(showSessionExpiryWarning, timeoutDuration * 1000);
                };
            }

            function resetSessionTimer() {
                const xhr = new XMLHttpRequest();
                xhr.open('POST', 'reset_session.php', true);
                xhr.setRequestHeader('Content-Type', 'application/x-www-form-urlencoded');
                xhr.onload = function() {
                    if (xhr.status === 200) {
                        console.log('Session reset successfully.');
                    } else {
                        console.error('Failed to reset session.');
                    }
                };
                xhr.send('action=reset_session');
            }
        })();
    </script>
    <!-- Incluir script.js primero -->
    <script src="script.js"></script>
    <!-- Incluir previous-games.js después de script.js -->
    <script src="previous-games.js"></script>
    <!-- Modal de confirmación de nuevo juego -->
    <div id="new-game-modal" class="modal">
        <div class="modal-content">
            <h2>New Game Confirmation</h2>
            <p>Is this going to be a new game?</p>
            <div class="modal-buttons">
                <button id="new-game-yes-button" class="modal-button">Yes</button>
                <button id="new-game-no-button" class="modal-button">No</button>
            </div>
        </div>
    </div>
</body>
</html>
