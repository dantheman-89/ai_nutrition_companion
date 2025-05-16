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
}

// Reset UI state after an error


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
    elements.recordBtn.classList.remove('bg-indigo-500');
    elements.recordBtn.classList.add('bg-red-500');
    elements.recordBtn.innerHTML = '<span class="mr-2">⏹️</span> Stop';
  } else {
    elements.recordBtn.classList.add('bg-indigo-500');
    elements.recordBtn.classList.remove('bg-red-500');
    elements.recordBtn.innerHTML = '<span class="mr-2">🎤</span> Talk';
  }
  elements.recordBtn.disabled = false;
}


 // Create a new message bubble in the chat
function createMessageBubble(sender, initialText) {
  const bubbleDiv = document.createElement("div");
  bubbleDiv.textContent = initialText;
  if (sender === "user") {
    bubbleDiv.className = "self-end bg-blue-100 rounded p-2 max-w-xs";
  } else { // AI
    bubbleDiv.className = "self-start bg-gray-100 rounded p-2 max-w-xs";
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
  elements.debugEl.classList.remove("hidden");
  elements.debugEl.textContent += msg + "\n";
  if (elements.debugEl.textContent.length > 1000) {
    elements.debugEl.textContent = elements.debugEl.textContent.slice(-1000);
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
  connectionState
};

// Allow other modules to update these states
