// UI Module - Handles DOM interactions and UI updates

// Cache DOM elements
const elements = {
  connectBtn: document.getElementById("connect"), // buttons at the bottom
  inputEl: document.getElementById("input"), // text input bar at the bottom
  sendBtn: document.getElementById("send"), // text send buttons at the bottom
  recordBtn: document.getElementById("record"), // buttons at the bottom
  messagesDiv: document.getElementById("messages"), // for debugging
  debugEl: document.getElementById("debug") // for debugging
};

// Debugging configuration
const DEBUG = true;

// UI State 
let connectionState = "DISCONNECTED"; // "DISCONNECTED", "CONNECTING", "CONNECTED"


// Initialize UI elements and set up initial state
function initializeUI() {
  updateConnectionUI("DISCONNECTED");
  
  // Add window resize handler to adjust message container height
  window.addEventListener('resize', adjustMessageContainerHeight);
  
  // Initial adjustment
  adjustMessageContainerHeight();
}

// Add this new function
function adjustMessageContainerHeight() {
  const headerHeight = document.querySelector('.app-header').offsetHeight;
  const controlsHeight = document.querySelector('.input-controls-section').offsetHeight;
  
  // Calculate and set the messages container height
  const messagesHeight = window.innerHeight - headerHeight - controlsHeight;
  document.getElementById('messages').style.height = `${messagesHeight}px`;
}


// Update UI based on connection state
function updateConnectionUI(state) {
  connectionState = state;
  
  // Update button text and state
  switch(state) {
    case "DISCONNECTED":
      elements.connectBtn.textContent = "Connect";
      elements.connectBtn.disabled = false;
      elements.recordBtn.disabled = true; // Disable recording when disconnected
      break;
      
    case "CONNECTING":
      elements.connectBtn.textContent = "Connecting...";
      elements.connectBtn.disabled = true;
      elements.recordBtn.disabled = true;
      break;
      
    case "CONNECTED":
      elements.connectBtn.textContent = "Disconnect";
      elements.connectBtn.disabled = false;
      elements.recordBtn.disabled = false; // Enable recording when connected
      break;
  }
}

// Record button UI management
function updateButtonUI(isActive) {
  if (isActive) {
    // Use classes instead of inline styles
    elements.recordBtn.classList.add('recording');
    
    // Change to send icon when recording with a smaller size
    elements.recordBtn.innerHTML = `
      <svg class="send-icon-recording" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"></path>
      </svg>
    `;
  } else {
    // Remove the recording class
    elements.recordBtn.classList.remove('recording');
    
    // Restore to mic icon when not recording
    elements.recordBtn.innerHTML = `
      <svg class="mic-icon" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
        <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z"></path>
        <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z"></path>
      </svg>
    `;
  }
  elements.recordBtn.disabled = false;
}

 // Create a new message bubble in the chat
function createMessageBubble(sender, initialText) {
  const bubbleDiv = document.createElement("div");
  bubbleDiv.textContent = initialText;
  if (sender === "user") {
    // Only use the base classes, not Tailwind classes since we defined them in CSS
    bubbleDiv.className = "message-bubble user-message";
  } else { // AI
    bubbleDiv.className = "message-bubble ai-message";
  }
  elements.messagesDiv.appendChild(bubbleDiv);
  scrollToBottom();
  return bubbleDiv;
}

function scrollToBottom() {
  elements.messagesDiv.scrollTop = elements.messagesDiv.scrollHeight;
}

// ---------------------------------------------------------
// Debuging UI - Log debug messages if debugging is enabled
// ---------------------------------------------------------

function debug(msg) {
  if (!DEBUG) return;
  
  console.log(msg);
  
  // Make sure the debug element exists
  if (elements.debugEl) {
    
    // Append message with timestamp
    const timestamp = new Date().toLocaleTimeString();
    elements.debugEl.textContent += `[${timestamp}] ${msg}\n`;
    
    // Trim if content gets too long
    if (elements.debugEl.textContent.length > 5000) {
      const lines = elements.debugEl.textContent.split('\n');
      // Keep the last 50 lines
      elements.debugEl.textContent = lines.slice(-50).join('\n');
    }
    
    // Auto-scroll to bottom
    elements.debugEl.scrollTop = elements.debugEl.scrollHeight;
  }
}


// ---------------------------------------------------------
// Export public API
// ---------------------------------------------------------

export {
  elements,
  initializeUI,
  updateConnectionUI,
  updateButtonUI,
  createMessageBubble,
  debug,
  scrollToBottom,
  connectionState,
  adjustMessageContainerHeight
};

// Allow other modules to update these states
