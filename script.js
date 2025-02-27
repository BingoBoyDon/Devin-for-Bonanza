// script.js

// Variables globales
let currentGameNumber = 0;
let siteId = new URLSearchParams(window.location.search).get('site_id');
let macAddress = ""; // Variable para almacenar la dirección MAC
let sequence = []; // Array para almacenar la secuencia de números seleccionados

// Evento que se ejecuta cuando el DOM está completamente cargado
document.addEventListener("DOMContentLoaded", function() {
    // Check if configValue is '0' and display the toaster message
    if (configValue === '0') {
        showMessage("Cannot do the bingo draw because it is not yet scheduled", "info", 15000);
    }
    // Obtener el número de juego actual desde el servidor
    fetch(`fetch_game_number.php?site_id=${siteId}`)
        .then(response => response.text())
        .then(gameNumber => {
            currentGameNumber = parseInt(gameNumber, 10);
            console.log("Current game number: ", currentGameNumber);
            document.getElementById('game-number').textContent = currentGameNumber;
        })
        .catch(error => console.error('Error fetching the game number:', error));

    // Generar las cajas de números para cada columna
    generateNumberBoxes('B', 1, 15);
    generateNumberBoxes('I', 16, 30);
    generateNumberBoxes('N', 31, 45);
    generateNumberBoxes('G', 46, 60);
    generateNumberBoxes('O', 61, 75);

    // Actualizar la visualización inicial de la secuencia de números seleccionados
    updateSequenceDisplay();
});

/**
 * Función para generar las cajas de números dentro de cada columna.
 * @param {string} parent - El ID de la columna (B, I, N, G, O).
 * @param {number} start - El número inicial de la columna.
 * @param {number} end - El número final de la columna.
 */
function generateNumberBoxes(parent, start, end) {
    const column = document.getElementById(parent);
    console.log("Config Value received in JS:", configValue); // Verificar el valor recibido

    for (let i = start; i <= end; i++) {
        const numberBox = document.createElement('div');
        numberBox.textContent = i.toString().padStart(2, '0');
        numberBox.dataset.number = `${parent} ${i}`;
        numberBox.dataset.letter = parent;
        numberBox.classList.add(`color-${parent}`);

        // Verificar si configValue es '1'
        if (configValue === '1') {
            console.log(`Number ${i} is enabled for click.`);
            numberBox.addEventListener('click', function () {
                // Obtener el cellId (por ejemplo, "B1")
                const cellId = `${parent}${i}`;
                
                // Si no tenemos la dirección MAC, obtenerla
                if (!macAddress) {
                    if (typeof sendWebsocketMessage === "function" && typeof getMacAddress === "function") {
                        getMacAddress(siteId).then(mac => {
                            if (mac) {
                                macAddress = mac;
                                // Enviar el mensaje al servidor websocket
                                sendWebsocketMessage(cellId, macAddress);
                            }
                        });
                    } else {
                        console.error("Required functions are not defined");
                    }
                } else {
                    // Ya tenemos la dirección MAC, enviar el mensaje directamente
                    if (typeof sendWebsocketMessage === "function") {
                        sendWebsocketMessage(cellId, macAddress);
                    } else {
                        console.error("sendWebsocketMessage function is not defined");
                    }
                }
                
                if (!this.classList.contains('marked') && sequence.length < 30) {
                    this.classList.add('marked');
                    const currentSequence = sequence.length + 1;
                    this.setAttribute('data-sequence', currentSequence);
                    sequence.push(`${parent} ${i}`);
                    this.classList.add('fade-in');
                    this.addEventListener('animationend', () => {
                        this.classList.remove('fade-in');
                    });

                    if (sequence.length === 30) {
                        showMessage("The limit of 30 drawn numbers has been reached.", "info");
                        checkLastSequence();
                    }
                } else if (this.classList.contains('marked')) {
                    // Enviar mensaje de reset cuando se desmarca un número
                    if (typeof sendWebsocketMessage === "function") {
                        sendWebsocketMessage(cellId, macAddress, "reset");
                    } else {
                        console.error("sendWebsocketMessage function is not defined");
                    }
                    
                    const lastNumber = sequence[sequence.length - 1];
                    const lastSelected = `${parent} ${i}` === lastNumber;
                    if (lastSelected) {
                        this.classList.remove('marked');
                        this.removeAttribute('data-sequence');
                        sequence.pop();
                    } else {
                        // Permitir desmarcar cualquier número, no solo el último
                        const index = sequence.indexOf(`${parent} ${i}`);
                        if (index !== -1) {
                            this.classList.remove('marked');
                            this.removeAttribute('data-sequence');
                            sequence.splice(index, 1);
                            
                            // Actualizar los números de secuencia para los elementos restantes
                            document.querySelectorAll('.column div.marked').forEach((element, idx) => {
                                element.setAttribute('data-sequence', idx + 1);
                            });
                        } else {
                            const lastNumberSplit = lastNumber.split(" ");
                            const lastNumberToUnmark = lastNumberSplit[1];
                            showMessage(`Please unmark number ${lastNumberToUnmark} first.`, "info");
                        }
                    }
                } else {
                    if (sequence.length >= 30) {
                        showMessage("You cannot select more than 30 numbers.", "info");
                    }
                }
                updateSequenceDisplay();
            });
        } else {
            console.log(`Number ${i} is disabled for click.`);
            numberBox.classList.add('disabled'); // Añadir clase para deshabilitar el clic
        }

        column.appendChild(numberBox);
    }
}

/**
 * Función para actualizar la visualización de la secuencia de números seleccionados.
 */
function updateSequenceDisplay() {
    const sequenceContainer = document.getElementById('sequence-container');
    sequenceContainer.innerHTML = ''; // Limpiar contenido previo

    // Crear 30 cajas para los números de la secuencia
    for (let i = 0; i < 30; i++) {
        const seqBox = document.createElement('div');
        if (i < sequence.length) {
            let num = sequence[i].split(" ")[1]; // Obtener el número
            seqBox.textContent = num;
            seqBox.classList.add('filled', 'fade-in'); // Añadir clases para estilo
            seqBox.addEventListener('animationend', () => seqBox.classList.remove('fade-in'));
        } else {
            seqBox.textContent = i + 1; // Mostrar número de posición
            seqBox.classList.remove('filled'); // Remover clase si no está seleccionado
        }
        sequenceContainer.appendChild(seqBox);
    }

    const setBingoButton = document.getElementById('set-bingo-button');
    if (sequence.length === 30) {
        setBingoButton.style.display = 'inline-block'; // Mostrar botón
    } else {
        setBingoButton.style.display = 'none'; // Ocultar botón
    }

    // Ocultar los botones "Go Back" y "Previous Games" si hay al menos un número seleccionado
    const goBackButton = document.getElementById('go-back-button');
    const previousGamesButton = document.getElementById('previous-games-button');
    if (sequence.length > 0) {
        goBackButton.style.display = 'none';
        previousGamesButton.style.display = 'none';
    } else {
        goBackButton.style.display = 'inline-block';
        previousGamesButton.style.display = 'inline-block';
    }

    console.log("Selected numbers updated:", sequence);
}

/**
 * Función para reiniciar el Bingo, desmarcando todos los números seleccionados.
 */
function resetBingo() {
    // Enviar mensajes de reset para todos los números
    if (typeof sendResetAllMessages === "function" && macAddress) {
        sendResetAllMessages(macAddress);
    } else {
        console.error("sendResetAllMessages function is not defined or MAC address is not available");
    }
    
    sequence = []; // Limpiar el array de secuencia
    document.querySelectorAll('.column div.marked').forEach(element => {
        element.classList.remove('marked'); // Remover clase marcada
        element.removeAttribute('data-sequence'); // Eliminar el atributo data-sequence
    });
    updateSequenceDisplay(); // Actualizar visualización de la secuencia
    document.getElementById('set-bingo-button').style.display = 'none'; // Ocultar botón "Set Bingo"

    // Mostrar nuevamente los botones "Go Back" y "Previous Games"
    const goBackButton = document.getElementById('go-back-button');
    const previousGamesButton = document.getElementById('previous-games-button');
    goBackButton.style.display = 'inline-block';
    previousGamesButton.style.display = 'inline-block';
}

// Evento al hacer clic en el botón "Reset Selected"
document.getElementById('reset-bingo-button').addEventListener('click', resetBingo);
 * @param {string} type - The type of message: 'error', 'success', 'info', 'warning'.
 * @param {number} duration - (Optional) Duration in milliseconds to display the message.
 * @param {function} callback - (Optional) Function to call after the message hides.
 */
function showMessage(message, type = "info", duration = 3000, callback = null) {
    const toastContainer = document.getElementById('toast-container');

    // Crear un nuevo elemento de mensaje
    const messageElement = document.createElement('div');
    messageElement.textContent = message;
    messageElement.classList.add('toast', type);

    // Agregar el mensaje al contenedor
    toastContainer.appendChild(messageElement);

    // Mostrar el mensaje con una pequeña animación (opcional)
    setTimeout(() => {
        messageElement.classList.add('show');
    }, 10);

    // Ocultar el mensaje después de la duración especificada
    setTimeout(() => {
        messageElement.classList.remove('show');
        // Remover el mensaje del DOM después de la transición
        setTimeout(() => {
            toastContainer.removeChild(messageElement);
            if (typeof callback === 'function') {
                callback();
            }
        }, 300); // Tiempo para que la transición termine
    }, duration);
}



/**
 * Función para deshabilitar o habilitar botones y controlar el spinner con un mensaje.
 * @param {boolean} state - True para deshabilitar botones y mostrar spinner, false para habilitar botones y ocultar spinner.
 * @param {string} message - El mensaje a mostrar con el spinner.
 */
function disableButtons(state, message = '') {
    const buttons = document.querySelectorAll('#go-back-button, #reset-bingo-button, #set-bingo-button, #previous-games-button');
    buttons.forEach(button => {
        button.disabled = state;
    });

    const spinnerContainer = document.getElementById('spinner-container');
    const spinnerMessage = document.getElementById('spinner-message');
    if (spinnerContainer) {
        if (state) {
            spinnerContainer.style.display = 'block';
            spinnerMessage.textContent = message;
        } else {
            spinnerContainer.style.display = 'none';
            spinnerMessage.textContent = '';
        }
    }
}

/**
 * Función para verificar si la secuencia ha sido seleccionada anteriormente.
 */
function checkLastSequence() {
    console.log("checkLastSequence() has been called.");

    const siteIdParam = siteId;
    console.log("siteId obtained:", siteIdParam);

    // Extraer solo los números de la secuencia
    const sequenceNumbers = sequence.map(item => parseInt(item.split(" ")[1], 10));
    console.log("Selected number sequence:", sequenceNumbers);

    // Validar que exactamente 30 números han sido extraídos y son válidos
    if (sequenceNumbers.length !== 30 || sequenceNumbers.some(isNaN)) {
        showMessage("Error extracting the sequence of numbers.", "error");
        console.error("Error extracting the sequence of numbers.");
        return;
    }

    // Enviar la secuencia al servidor para verificación
    fetch('check_last_sequence.php', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ siteId: siteIdParam, sequence: sequenceNumbers }),
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(data => {
        console.log("Server response:", data);
        if (data.error) {
            showMessage(`Error verifying the sequence: ${data.error}`, "error");
            console.error("Error verifying the sequence:", data.error);
            return;
        }
        if (data.match) {
            showMessage("These numbers have already been selected.", "warning");
            // Deshabilitar y ocultar el botón "Set Bingo"
            const setBingoButton = document.getElementById('set-bingo-button');
            setBingoButton.disabled = true;
            setBingoButton.style.display = 'none';
            console.log("Set Bingo button disabled and hidden.");
            // Mostrar los botones "Go Back" y "Previous Games"
            const goBackButton = document.getElementById('go-back-button');
            const previousGamesButton = document.getElementById('previous-games-button');
            goBackButton.style.display = 'inline-block';
            previousGamesButton.style.display = 'inline-block';
        } else {
            // Habilitar y mostrar el botón "Set Bingo"
            const setBingoButton = document.getElementById('set-bingo-button');
            setBingoButton.disabled = false;
            setBingoButton.style.display = 'inline-block';
            console.log("Set Bingo button enabled and shown.");
            // Ocultar los botones "Go Back" y "Previous Games"
            const goBackButton = document.getElementById('go-back-button');
            const previousGamesButton = document.getElementById('previous-games-button');
            goBackButton.style.display = 'none';
            previousGamesButton.style.display = 'none';
        }
    })
    .catch(error => {
        console.error('Error verifying the sequence:', error);
        showMessage("An error occurred while verifying the sequence.", "error");
    });
}

/**
 * Función para establecer Bingo enviando los números seleccionados al servidor.
 */
function setBingo() {
    const gameNumber = currentGameNumber;
    const userId = new URLSearchParams(window.location.search).get('user_id');

    console.log("Game Number:", gameNumber);
    console.log("Site ID:", siteId);
    console.log("User ID:", userId);

    const selectedNumbersElements = document.querySelectorAll('.column div.marked');
    const numbers = Array.from(selectedNumbersElements).map(el => {
        const sequence = parseInt(el.getAttribute('data-sequence'), 10);
        return {
            letter: el.dataset.letter, // Correctamente definido en generateNumberBoxes
            number: parseInt(el.textContent, 10),
            sequence: sequence
        };
    }).filter(item => !isNaN(item.sequence));

    console.log("Numbers:", numbers);

    if (gameNumber === 0 || !siteId || !userId || numbers.length === 0) {
        showMessage("Invalid game number, site ID, user ID, or no numbers selected.", "error");
        return;
    }

    // Mostrar un indicador de carga o deshabilitar botones según sea necesario
    disableButtons(true, "Inserting numbers, please wait...");
    showMessage("Inserting numbers, please wait...", "info");

    fetch('insert-bingo-numbers.php', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ gameNumber, siteId, userId, numbers }),
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Network response was not ok');
        }
        return response.json();
    })
    .then(data => {
        if (data.error) {
            console.error("Error inserting numbers:", data.error);
            showMessage(`Error inserting numbers: ${data.error}`, "error");
            disableButtons(false);
        } else {
            showMessage("Bingo has been successfully inserted.", "success");
            resetBingo();
            updateGameNumber();

            // Start checking status after inserting bingo numbers
            checkStatus(gameNumber, siteId);
        }
    })
    .catch(error => {
        console.error('Fetch error:', error);
        showMessage("It seems that this game number has not been processed.", "error");
        disableButtons(false);
    });
}

/**
 * Función para verificar el estado de draw_delivered y numbers_delivered después de presionar 'Set Bingo'.
 */
function checkStatus(gameNumber, siteId) {
    let attempts = 0;
    const maxAttempts = 6;
    const interval = 5000; // Interval between status checks in milliseconds

    // Show the spinner with the message
    disableButtons(true, "Working, please wait...");

    const check = () => {
        fetch(`check_status.php?game_number=${gameNumber}&site_id=${siteId}`)
            .then(response => response.json())
            .then(data => {
                console.log("Status data received:", data); // Debugging output
                if (data.error) {
                    console.error("Error checking status:", data.error);
                    showMessage(`Error checking status: ${data.error}`, "error", 5000);
                    disableButtons(false);
                } else {
                    if (data.draw_delivered && data.draw_delivered !== null) {
                        // Show the message 'The photo was created.'
                        showMessage("The photo was created.", "success", 5000);

                        // Now focus on numbers_delivered
                        checkNumbersDelivered();
                    } else {
                        // Retry checking draw_delivered
                        attempts++;
                        if (attempts < maxAttempts) {
                            setTimeout(check, interval);
                        } else {
                            // After max attempts, show message and log out
                            showMessage("Numbers saved to be inserted when the server is online.", "info", 6000, () => {
                                // Log out the user after the message duration ends
                                window.location.href = 'logout.php';
                            });

                            // Hide the spinner and enable buttons
                            disableButtons(false);
                        }
                    }
                }
            })
            .catch(error => {
                console.error('Fetch error:', error);
                showMessage("An error occurred while checking the status.", "error", 5000);
                disableButtons(false);
            });
    };

    const checkNumbersDelivered = () => {
        let numberAttempts = 0;
        const maxNumberAttempts = 3;

        const checkNumbers = () => {
            fetch(`check_status.php?game_number=${gameNumber}&site_id=${siteId}`)
                .then(response => response.json())
                .then(data => {
                    console.log("Numbers status data received:", data); // Debugging output
                    if (data.error) {
                        console.error("Error checking numbers_delivered:", data.error);
                        showMessage(`Error checking numbers_delivered: ${data.error}`, "error", 5000);
                        disableButtons(false);
                    } else {
                        if (data.numbers_delivered === true || data.numbers_delivered === "true" || data.numbers_delivered === "t") {
                            // Show the message 'Numbers were inserted on the server.'
                            showMessage("Numbers were inserted on the server.", "success", 15000, () => {
                                // Log out the user after the message duration ends
                                window.location.href = 'logout.php';
                            });

                            // Hide the spinner and enable buttons
                            disableButtons(false);
                        } else {
                            numberAttempts++;
                            if (numberAttempts < maxNumberAttempts) {
                                setTimeout(checkNumbers, interval);
                            } else {
                                // After max attempts, show message and log out
                                showMessage("We have saved your numbers. They will be added when the server is online.", "info", 15000, () => {
                                    // Log out the user after the message duration ends
                                    window.location.href = 'logout.php';
                                });

                                // Hide the spinner and enable buttons
                                disableButtons(false);
                            }
                        }
                    }
                })
                .catch(error => {
                    console.error('Fetch error:', error);
                    showMessage("An error occurred while checking numbers_delivered status.", "error", 5000);
                    disableButtons(false);
                });
        };

        // Start the first numbers_delivered check after the interval
        setTimeout(checkNumbers, interval);
    };

    // Start the first draw_delivered check immediately
    check();
}

/**
 * Función para actualizar el número de juego desde el servidor.
 */
function updateGameNumber() {
    fetch(`fetch_game_number.php?site_id=${siteId}`)
        .then(response => response.text())
        .then(gameNumber => {
            currentGameNumber = parseInt(gameNumber, 10);
            console.log("Current game number: ", currentGameNumber);
            document.getElementById('game-number').textContent = currentGameNumber;
        })
        .catch(error => console.error('Error fetching the game number:', error));
}

// Función para inicializar la dirección MAC después de que todos los scripts estén cargados
window.addEventListener('load', function() {
    // Obtener la dirección MAC al cargar la página
    if (typeof getMacAddress === 'function') {
        getMacAddress(siteId).then(mac => {
            if (mac) {
                macAddress = mac;
                console.log("MAC address initialized:", macAddress);
            }
        });
    } else {
        console.error("getMacAddress function is not defined");
    }
});
