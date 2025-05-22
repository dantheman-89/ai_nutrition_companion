// Main entry point - Orchestrates the application
import * as UI from './js/ui.js';
import * as Audio from './js/audio.js';
import * as WSClient from './js/wsclient.js';


// Initialize app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  // Initialize UI
  UI.initializeUI();
  UI.initializeCollapsiblePanels(); 
  UI.setupPhotoUploadLogic();   
  
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

  // Estimate Nutrition button
  if (UI.elements.estimatePhotosBtn) {
    UI.elements.estimatePhotosBtn.addEventListener('click', () => {
      const files = UI.elements.mealPhotoInput.files;
      if (files && files.length > 0) {
        const fileNames = Array.from(files).map(file => file.name);
        
        if (WSClient.isConnected()) {
          WSClient.sendMealPhotoForEstimation(fileNames);
          // Optionally, provide UI feedback, e.g., disable button, show loading
          UI.elements.estimatePhotosBtn.disabled = true;
          UI.elements.estimatePhotosBtn.textContent = 'Estimating...';
          // You'll need to re-enable it when a response is received or on error
        } 
      } 
    });
  } 

  // Load Weekly Review button
  if (UI.elements.loadWeeklyReviewBtn) {
    UI.elements.loadWeeklyReviewBtn.addEventListener('click', () => {
      if (WSClient.isConnected()) {
        if (WSClient.requestWeeklyReviewData()) {
          // Optionally, provide UI feedback that data is being loaded
          UI.elements.loadWeeklyReviewBtn.disabled = true;
          UI.elements.loadWeeklyReviewBtn.textContent = 'Loading Review...';
          // The button will be re-enabled by the success/error handling 
          // or if requestWeeklyReviewData returns false (e.g., not connected)
          // For now, we assume success will lead to data display which might implicitly re-enable.
          // A more robust solution would re-enable it in the weekly_review_data handler or on error.
        }
      } else {
        // Handle case where not connected, e.g., show a message
        UI.debug("Cannot load weekly review: Not connected.");
        // alert("Not connected. Please connect first."); // Example user feedback
      }
    });
  }

}