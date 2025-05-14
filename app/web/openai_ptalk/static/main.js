// Main entry point - Orchestrates the application
import * as UI from './js/ui.js';
import * as Audio from './js/audio.js';
import * as WebSocket from './js/websocket.js';


// Initialize the application
function initApp() {
  // Set up UI
  UI.initializeUI();
  
  // Set up event listeners
  UI.elements.sendBtn.addEventListener("click", WebSocket.handleSendButtonClick);
  UI.elements.inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      WebSocket.handleSendButtonClick();
    }
  });
  UI.elements.recordBtn.addEventListener("click", Audio.toggleAudioCapture);
  UI.elements.connectBtn.addEventListener("click", WebSocket.handleConnectionToggle);
  
  // Initialize audio context
  try {
    Audio.getAudioContext();
    UI.debug("AudioContext obtained/initialized.");
  } catch (e) {
    console.error(`Fatal: Error initializing audio context: ${e}`);
    UI.debug("AudioContext initialization failed.");
    UI.elements.recordBtn.disabled = true;
    UI.elements.recordBtn.title = "Audio context failed to initialize.";
  }
}

// Initialize on DOM content loaded
document.addEventListener("DOMContentLoaded", initApp);

// Keep audio context running
document.body.addEventListener("click", () => {
  const ctx = Audio.getAudioContext();
  if (ctx && ctx.state === 'suspended') {
    UI.debug("Body click detected, resuming suspended AudioContext...");
    ctx.resume().then(() => {
      UI.debug(`AudioContext resumed. State: ${ctx.state}`);
    }).catch(e => {
      console.error("Error resuming AudioContext on click:", e);
      UI.debug(`Error resuming AudioContext: ${e.message}`);
    });
  }
});