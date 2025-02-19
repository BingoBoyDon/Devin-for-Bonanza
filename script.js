// script.js
// -------------------------------------------------------------------
// Nota: Este archivo se debe cargar como módulo, por ejemplo:
// <script type="module" src="script.js"></script>
// -------------------------------------------------------------------

import { applyEffect } from './modulo/animationManager.js';
import { applyTextEffect } from './modulo/textEffects.js';

// Variables y configuración inicial
const defaultImage = '/tec-area/kioks-web/images/X.png';
const images = {
  B: '/tec-area/kioks-web/images/B_RED.png',
  I: '/tec-area/kioks-web/images/I_BLUE.png',
  N: '/tec-area/kioks-web/images/N_YELOW.png',
  G: '/tec-area/kioks-web/images/G_GREN.png',
  O: '/tec-area/kioks-web/images/O_VIOLET.png'
};

const letters = ['B', 'I', 'N', 'G', 'O'];
let drawCount = 0;
const maxDraws = 30;
const drawCounterElement = document.getElementById('draw-counter');
let ws;
let connectionAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY = 5000;

// Generar dinámicamente el tablero de Bingo
letters.forEach((letter) => {
  const column = document.getElementById(letter);
  const startNumber = letters.indexOf(letter) * 15 + 1;
  const leftGroup = Array.from({ length: 7 }, (_, i) => `${letter}${startNumber + i}`);
  const rightGroup = Array.from({ length: 8 }, (_, i) => `${letter}${startNumber + 7 + i}`);

  const orderedNumbers = [];
  for (let i = 0; i < 8; i++) {
    if (i < leftGroup.length) orderedNumbers.push(leftGroup[i]);
    if (i < rightGroup.length) orderedNumbers.push(rightGroup[i]);
  }

  orderedNumbers.forEach((cellId) => {
    const cell = document.createElement('div');
    cell.className = 'cell';
    cell.id = cellId;

    const img = document.createElement('img');
    img.src = defaultImage;
    img.alt = `${cellId} image`;

    const span = document.createElement('span');
    span.textContent = cellId;

    cell.appendChild(img);
    cell.appendChild(span);
    column.appendChild(cell);
  });
});

// Generar la secuencia de draws
const sequenceGrid = document.getElementById('sequence-grid');
for (let i = 1; i <= 30; i++) {
  const sequenceCell = document.createElement('div');
  sequenceCell.className = 'sequence-cell';
  sequenceCell.id = `sequence${i}`;

  const img = document.createElement('img');
  img.src = defaultImage;
  img.alt = `Sequence ${i} image`;

  const idSpan = document.createElement('span');
  idSpan.className = 'sequence-id';
  idSpan.textContent = '';

  const numberSpan = document.createElement('span');
  numberSpan.className = 'sequence-number';
  numberSpan.textContent = i;

  sequenceCell.appendChild(img);
  sequenceCell.appendChild(idSpan);
  sequenceCell.appendChild(numberSpan);
  sequenceGrid.appendChild(sequenceCell);
}

function updateCounter(increment = true) {
  if (increment && drawCount < maxDraws) {
    drawCount++;
  } else if (!increment && drawCount > 0) {
    drawCount--;
  }
  drawCounterElement.textContent = `${drawCount} Draw${drawCount !== 1 ? 's' : ''}`;
}

function updateBoardCell(cellId, newImage, effect, options = {}) {
  const cell = document.getElementById(cellId);
  if (cell) {
    const img = cell.querySelector('img');
    applyEffect(img, "fadeOut", { duration: 0.3 }).then(() => {
      img.src = newImage ? newImage : images[cellId.charAt(0)];
      applyEffect(img, effect || "fadeIn", options);
    });
  }
}

function resetBoardCell(cellId) {
  const cell = document.getElementById(cellId);
  if (cell) {
    const img = cell.querySelector('img');
    applyEffect(img, "fadeOut", { duration: 0.3 }).then(() => {
      img.src = defaultImage;
      applyEffect(img, "fadeIn", { duration: 0.3 });
    });
  }
}

function updateSequence(cellId) {
  if (drawCount >= 1 && drawCount <= maxDraws) {
    const sequenceCell = document.getElementById(`sequence${drawCount}`);
    if (sequenceCell) {
      const img = sequenceCell.querySelector('img');
      const idSpan = sequenceCell.querySelector('.sequence-id');
      Promise.all([
        applyEffect(img, "fadeOut", { duration: 0.3 }),
        applyEffect(idSpan, "fadeOut", { duration: 0.3 })
      ]).then(() => {
        const boardCell = document.getElementById(cellId);
        if (boardCell) {
          const boardImgSrc = boardCell.querySelector('img').src;
          img.src = boardImgSrc;
          idSpan.textContent = cellId;
        }
        Promise.all([
          applyEffect(img, "fadeIn", { duration: 0.3 }),
          applyEffect(idSpan, "fadeIn", { duration: 0.3 })
        ]);
      });
    }
  }
}

function resetSequence() {
  if (drawCount >= 1 && drawCount <= maxDraws) {
    const sequenceCell = document.getElementById(`sequence${drawCount}`);
    if (sequenceCell) {
      const img = sequenceCell.querySelector('img');
      const idSpan = sequenceCell.querySelector('.sequence-id');
      Promise.all([
        applyEffect(img, "fadeOut", { duration: 0.3 }),
        applyEffect(idSpan, "fadeOut", { duration: 0.3 })
      ]).then(() => {
        img.src = defaultImage;
        idSpan.textContent = '';
        Promise.all([
          applyEffect(img, "fadeIn", { duration: 0.3 }),
          applyEffect(idSpan, "fadeIn", { duration: 0.3 })
        ]);
      });
    }
  }
}

function updateText(config) {
  const textsContent = document.getElementById('texts-content');
  if (!textsContent) return;

  const {
    text = "",
    fontFamily = "",
    fontSize = "",
    color = "",
    effect = ""
  } = config;

  if (textsContent.textContent !== text) {
    textsContent.textContent = text;
  }

  if (fontFamily) textsContent.style.fontFamily = fontFamily;
  if (fontSize) textsContent.style.fontSize = fontSize;
  if (color) textsContent.style.color = color;

  if (effect) {
    applyTextEffect(textsContent, effect, {
      duration: config.effectDuration || 1,
      delay: config.effectDelay || 0,
      easing: config.easing || 'ease'
    });
  } else {
    textsContent.classList.remove('blink-effect');
  }
}

function updatePhoto(data) {
  const localPath = "https://localhost:8443/";
  const containerId = data.targetContainer || 'photos-grid';
  const container = document.getElementById(containerId);
  
  if (!container) {
    console.error(`No se encontró el contenedor con id "${containerId}"`);
    return;
  }

  // Limpiar el contenedor
  container.innerHTML = '';

  // Crear el contenedor de la foto
  const photoItem = document.createElement('div');
  photoItem.classList.add('photo-item');

  const img = document.createElement('img');
  img.src = `${localPath}${data.filename}`;
  img.alt = `Foto: ${data.filename}`;
  
  // Función para notificar que el efecto ha finalizado
  const notifyEffectCompletion = () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.error('WebSocket no disponible. Reintentando conexión...');
      connectWebSocket();
      setTimeout(notifyEffectCompletion, 1000);
      return;
    }

    const message = {
      action: "effectCompleted",
      type: "photo",
      filename: data.filename,
      targetContainer: containerId
    };
    
    try {
      ws.send(JSON.stringify(message));
      console.log(`Notificación de efecto completado enviada: ${containerId}`);
    } catch (error) {
      console.error('Error enviando notificación:', error);
      setTimeout(notifyEffectCompletion, 1000);
    }
  };

  // Función de limpieza
  const cleanUp = () => {
    if (!data.keepFinalState && container.contains(photoItem)) {
      container.removeChild(photoItem);
    }
    notifyEffectCompletion();
  };

  photoItem.appendChild(img);
  container.appendChild(photoItem);

  if (data.effectIn && data.effectIn.trim() !== "") {
    applyEffect(photoItem, data.effectIn, { duration: data.effectDuration || 1 })
      .then(() => {
        setTimeout(() => {
          if (data.effectOut && data.effectOut.trim() !== "") {
            applyEffect(photoItem, data.effectOut, { duration: data.effectDuration || 1 })
              .then(cleanUp)
              .catch(err => {
                console.error("Error en effectOut de foto:", err);
                cleanUp();
              });
          } else {
            cleanUp();
          }
        }, (data.duration || 5) * 1000);
      })
      .catch(err => {
        console.error("Error en effectIn de foto:", err);
        cleanUp();
      });
  } else if (data.effect && data.effect.trim() !== "") {
    applyEffect(photoItem, data.effect, { duration: data.effectDuration || 1 })
      .then(cleanUp)
      .catch(err => {
        console.error("Error en effect de foto:", err);
        cleanUp();
      });
  } else {
    setTimeout(cleanUp, (data.duration || 5) * 1000);
  }
}

function updateVideo(data) {
  const containerId = data.targetContainer || 'videos-container';
  const container = document.getElementById(containerId);
  
  if (!container) {
    console.error(`No se encontró el contenedor con id "${containerId}"`);
    return;
  }

  // Limpiar contenedor y recursos
  container.style.background = "transparent";
  container.innerHTML = '';

  const videoItem = document.createElement('div');
  videoItem.classList.add('video-item');

  const videoEl = document.createElement('video');
  videoEl.src = data.videoUrl;
  videoEl.autoplay = true;
  videoEl.muted = true;
  videoEl.playsInline = true;
  videoEl.controls = false;
  videoEl.style.width = "100%";

  // Control de recursos y eventos
  let timeoutId = null;
  let notified = false;

  const cleanupListeners = () => {
    videoEl.removeEventListener('ended', handleEnded);
    videoEl.removeEventListener('error', handleError);
    videoEl.removeEventListener('loadeddata', handleLoaded);
    if (timeoutId) {
      clearTimeout(timeoutId);
      timeoutId = null;
    }
  };

  const handleLoaded = () => {
    console.log("Video cargado correctamente:", data.videoUrl);
  };

  const notifyEffectCompletion = () => {
    if (notified) return;
    notified = true;

    const checkAndSend = () => {
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        console.error('WebSocket no disponible. Reintentando conexión...');
        connectWebSocket();
        setTimeout(checkAndSend, 1000);
        return;
      }

      const message = {
        action: "effectCompleted",
        type: "video",
        videoUrl: data.videoUrl,
        targetContainer: containerId
      };

      try {
        ws.send(JSON.stringify(message));
        console.log(`Notificación de efecto completado enviada: ${containerId}`);
      } catch (error) {
        console.error('Error enviando notificación:', error);
        setTimeout(checkAndSend, 1000);
      }
    };

    checkAndSend();

    if (!data.keepFinalState && container.contains(videoItem)) {
      container.removeChild(videoItem);
    }
  };

  const handleEnded = () => {
    console.log("Evento 'ended' disparado en video");
    cleanupListeners();
    notifyEffectCompletion();
  };

  const handleError = (err) => {
    console.error("Error en el elemento video:", err);
    cleanupListeners();
    notifyEffectCompletion();
  };

  videoEl.addEventListener('ended', handleEnded);
  videoEl.addEventListener('error', handleError);
  videoEl.addEventListener('loadeddata', handleLoaded);

  // Fallback timeout
  timeoutId = setTimeout(() => {
    console.log("Fallback timeout para video");
    cleanupListeners();
    notifyEffectCompletion();
  }, (data.duration || 30) * 1000);

  videoItem.appendChild(videoEl);
  container.appendChild(videoItem);

  // Manejo de efectos visuales
  if (data.effectIn && data.effectIn.trim() !== "") {
    applyEffect(videoItem, data.effectIn, { duration: data.effectDuration || 1 })
      .catch(err => {
        console.error("Error en effectIn de video:", err);
        cleanupListeners();
        notifyEffectCompletion();
      });
  }

  // Forzar reproducción
  videoEl.play().catch(err => {
    console.error("Error reproduciendo video:", err);
    cleanupListeners();
    notifyEffectCompletion();
  });
}

function connectWebSocket() {
  if (ws) {
    ws.close();
    ws = null;
  }

  ws = new WebSocket('ws://localhost:6790');

  ws.onopen = () => {
    console.log('WebSocket conectado exitosamente.');
    connectionAttempts = 0;
  };

  ws.onmessage = (event) => {
    try {
      console.log('Mensaje recibido:', event.data);
      const data = JSON.parse(event.data);
      console.log('Datos parseados:', data);
      
      if (data.action === "updateBoardCell" && data.cellId) {
        console.log('Actualizando celda:', data.cellId);
        updateBoardCell(data.cellId, data.image, data.effect, {
          duration: data.duration,
          delay: data.delay,
          iterationCount: data.iterationCount,
          keepFinalState: data.keepFinalState
        });
        updateCounter(true);
        updateSequence(data.cellId);
      } else if (data.action === "reset" && data.cellId) {
        console.log('Reseteando celda:', data.cellId);
        resetBoardCell(data.cellId);
        resetSequence();
        updateCounter(false);
      } else if (data.action === "refresh") {
        console.log('Refrescando página');
        location.reload(true);
      } else if (data.action === "updateText") {
        console.log('Actualizando texto:', data);
        updateText(data);
      } else if (data.action === "updatePicture") {
        console.log('Actualizando foto:', data);
        updatePhoto(data);
      } else if (data.action === "updateVideo" && data.videoUrl) {
        console.log('Actualizando video:', data.videoUrl);
        updateVideo(data);
      } else {
        console.error('Formato de datos o acción no válidos:', data);
      }
    } catch (e) {
      console.error('Error al analizar JSON:', e);
    }
  };

  ws.onerror = (error) => {
    console.error('Error en WebSocket:', error);
  };

  ws.onclose = () => {
    console.log('WebSocket cerrado. Reintentando...');
    if (connectionAttempts < MAX_RECONNECT_ATTEMPTS) {
      connectionAttempts++;
      setTimeout(connectWebSocket, RECONNECT_DELAY * connectionAttempts);
    } else {
      console.error('Máximo de intentos de reconexión alcanzado');
      // Reiniciar contador después de un tiempo más largo
      setTimeout(() => {
        connectionAttempts = 0;
        connectWebSocket();
      }, RECONNECT_DELAY * 2);
    }
  };
}

// Iniciar conexión WebSocket
connectWebSocket();

// Hacer que los grids sean arrastrables y redimensionables
function makeDraggableResizable(el) {
  let isDragging = false;
  let isResizing = false;
  let startX, startY, startWidth, startHeight, startLeft, startTop;

  el.addEventListener('mousedown', function(e) {
    if (e.target.classList.contains('resizer')) return;
    isDragging = true;
    startX = e.clientX;
    startY = e.clientY;
    const rect = el.getBoundingClientRect();
    startLeft = rect.left;
    startTop = rect.top;
    document.body.style.userSelect = 'none';
  });

  const resizer = el.querySelector('.resizer');
  resizer.addEventListener('mousedown', function(e) {
    isResizing = true;
    startX = e.clientX;
    startY = e.clientY;
    const rect = el.getBoundingClientRect();
    startWidth = rect.width;
    startHeight = rect.height;
    document.body.style.userSelect = 'none';
    e.stopPropagation();
    e.preventDefault();
  });

  document.addEventListener('mousemove', function(e) {
    if (isDragging) {
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      let newLeft = startLeft + dx;
      let newTop = startTop + dy;
      const windowWidth = window.innerWidth;
      const windowHeight = window.innerHeight;
      const elRect = el.getBoundingClientRect();
      const elWidth = elRect.width;
      const elHeight = elRect.height;
      newLeft = Math.min(Math.max(newLeft, 0), windowWidth - elWidth);
      newTop = Math.min(Math.max(newTop, 0), windowHeight - elHeight);
      el.style.left = `${newLeft}px`;
      el.style.top = `${newTop}px`;
    }
    if (isResizing) {
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      let newWidth = startWidth + dx;
      let newHeight = startHeight + dy;
      newWidth = Math.max(newWidth, 300);
      newHeight = Math.max(newHeight, 200);
      const windowWidth = window.innerWidth;
      const windowHeight = window.innerHeight;
      newWidth = Math.min(newWidth, windowWidth - el.offsetLeft);
      newHeight = Math.min(newHeight, windowHeight - el.offsetTop);
      el.style.width = `${newWidth}px`;
      el.style.height = `${newHeight}px`;
    }
  });

  document.addEventListener('mouseup', function() {
    if (isDragging || isResizing) {
      saveState();
    }
    isDragging = false;
    isResizing = false;
    document.body.style.userSelect = 'auto';
  });

  function saveState() {
    const id = el.id;
    const rect = el.getBoundingClientRect();
    const state = {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height
    };
    localStorage.setItem(`${id}State`, JSON.stringify(state));
  }

  function loadState() {
    const id = el.id;
    const saved = localStorage.getItem(`${id}State`);
    if (saved) {
      const state = JSON.parse(saved);
      el.style.left = `${state.left}px`;
      el.style.top = `${state.top}px`;
      el.style.width = `${state.width}px`;
      el.style.height = `${state.height}px`;
    } else {
      // Posiciones y tamaños por defecto
      if (id === 'board') {
        el.style.left = '100px';
        el.style.top = '100px';
        el.style.width = '500px';
        el.style.height = '600px';
      } else if (id === 'sequence') {
        el.style.left = '700px';
        el.style.top = '100px';
        el.style.width = '800px';
        el.style.height = '150px';
      } else if (id === 'photos') {
        el.style.left = '100px';
        el.style.top = '700px';
        el.style.width = '600px';
        el.style.height = '300px';
      } else if (id === 'texts') {
        el.style.left = '800px';
        el.style.top = '300px';
        el.style.width = '300px';
        el.style.height = '300px';
      }
    }
  }

  loadState();
}

document.querySelectorAll('.grid').forEach(makeDraggableResizable);
