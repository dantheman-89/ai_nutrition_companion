// Main entry point - Orchestrates the application
import * as UI from './js/ui.js';
import * as Audio from './js/audio.js';
import * as WSClient from './js/wsclient.js';


// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  // Initialize UI
  UI.initializeUI();
  
  // Set up event listeners
  setupEventListeners();
});

// Start up screen "Tap to Start" event listener
function setupEventListeners() {
  // Startup screen "Tap to Start"
  UI.elements.startupCircle.addEventListener('click', () => {
    // Prevent multiple rapid clicks
    UI.elements.startupCircle.style.pointerEvents = 'none'; 
    
    // 1) Connect the socket
    // updateConnectionUI("CONNECTING") will be called by WSClient.connect() via its own logic
    WSClient.connect(); 

    // Update text and animation speed
    UI.elements.startupText.innerText = 'Connecting';
    UI.elements.startupCircle.style.animationDuration = '0.8s';

    // 2) Wait for 4.5 seconds
    setTimeout(() => {
      // 3) The chat screen appears
      UI.showChatScreen();
    }, 4500);
  });

  // Connect button (in the main app screen)
  UI.elements.connectBtn.addEventListener('click', () => {
    if (WSClient.isConnected()) {
      WSClient.disconnect();
    } else {
      WSClient.connect(); // Allows re-connecting if initial attempt failed or user disconnected
    }
  });
  
  // Record button
  UI.elements.recordBtn.addEventListener('click', () => {
    if (Audio.isRecording) {
      Audio.stopAudioCapture();
    } else {
      Audio.startAudioCapture(WSClient.isConnected(), WSClient.getWebSocket());
    }
  });
  
  // Send button
  UI.elements.sendBtn.addEventListener('click', () => {
    const text = UI.elements.inputEl.value.trim();
    if (text) {
      WSClient.sendTextMessage(text);
      UI.createMessageBubble('user', text);
      UI.elements.inputEl.value = '';
    }
  });
}