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

function setupEventListeners() {
  // Connect button
  UI.elements.connectBtn.addEventListener('click', () => {
    if (WSClient.isConnected()) {
      WSClient.disconnect();
    } else {
      WSClient.connect();
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