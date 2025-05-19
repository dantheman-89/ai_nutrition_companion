// UI Module - Handles DOM interactions and UI updates

// Cache DOM elements
const elements = {
  startupScreen: document.getElementById('startup-screen'),
  startupCircle: document.getElementById('startup-circle'),
  startupText: document.getElementById('startup-text'),
  appContainer: document.getElementById('app-container'),
  connectBtn: document.getElementById("connect"), // connect button at the bottom
  inputEl: document.getElementById("input"), // text input bar at the bottom
  sendBtn: document.getElementById("send"), // text send buttons at the bottom
  recordBtn: document.getElementById("record"), // record button at the bottom
  messagesDiv: document.getElementById("messages"), // chat message section
  profileSection: document.getElementById('profile-section'), // profile section
  debugEl: document.getElementById("debug") // for debugging
};

// Debugging configuration
const DEBUG = true;

// ---------------------------------------------------------
// Start up screen and initialize chat screeen
// ---------------------------------------------------------

// UI State 
let connectionState = "DISCONNECTED"; // "DISCONNECTED", "CONNECTING", "CONNECTED"


// Initialize UI elements and set up initial state
function initializeUI() {
  elements.startupScreen.classList.remove('hidden'); // Show startup screen
  elements.appContainer.classList.add('hidden');    // Ensure app container is hidden
  elements.appContainer.classList.remove('visible');
  updateConnectionUI("DISCONNECTED");
  updateProfileDisplay({}); // Initialize profile section with placeholder
  
  // Add window resize handler to adjust message container height
  window.addEventListener('resize', adjustMessageContainerHeight);
}

// adjust height of the message container
function adjustMessageContainerHeight() {
  const headerHeight = document.querySelector('.app-header').offsetHeight;
  const controlsHeight = document.querySelector('.input-controls-section').offsetHeight;
  
  // Calculate and set the messages container height
  const messagesHeight = window.innerHeight - headerHeight - controlsHeight;
  document.getElementById('messages').style.height = `${messagesHeight}px`;
}

// transition from the startup screen to the main app
function showChatScreen() {
  elements.startupScreen.classList.add('hidden'); // Start fading out startup screen

  // Make app container ready for transition
  elements.appContainer.classList.remove('hidden'); 
  // Force a reflow/repaint before adding 'visible' to ensure transition plays
  void elements.appContainer.offsetWidth; 
  elements.appContainer.classList.add('visible'); // Trigger transition

  adjustMessageContainerHeight(); // Adjust height now that it's becoming visible
  elements.inputEl.focus(); // Optional: focus input field
}


// ---------------------------------------------------------
// Control UI elements 
// ---------------------------------------------------------

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

// ---------------------------------------------------------
// Chat UI elements 
// ---------------------------------------------------------

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
// User profile UI elements 
// ---------------------------------------------------------
// Function to update the profile display section
function updateProfileDisplay(msg) {
  if (!elements.profileSection) {
    debug("Profile section element not found.");
    return;
  }

  // Clear previous content
  elements.profileSection.innerHTML = ''; 

   // Extract the actual profile data from the message payload
  const profileData = msg && msg.data ? msg.data : {};

  // temp code for debugging
  // console.log("PROFILE_DATA received by updateProfileDisplay:", JSON.stringify(profileData, null, 2)); // <<< ADD THIS FOR DEBUGGING

  if (!profileData || Object.keys(profileData).length === 0) {
    elements.profileSection.innerHTML = `
      <div class="profile-placeholder p-4">
        <h3 class="text-xl font-semibold mb-2" style="color: var(--pingan-orange);">User Profile</h3>
        <p style="color: rgba(255, 255, 255, 0.7);">Profile information will be displayed here once available.</p>
      </div>`;
    debug("Profile data is empty, showing placeholder.");
    return;
  }

  debug("Updating profile display with new data.");
  const profileContainer = document.createElement('div');
  profileContainer.className = 'custom-scrollbar p-4 space-y-3 overflow-y-auto h-full'; // Added padding, spacing, and scroll

  for (const sectionTitle in profileData) {
    const sectionData = profileData[sectionTitle];
    if (typeof sectionData === 'object' && sectionData !== null && Object.keys(sectionData).length > 0) {
      const sectionDiv = document.createElement('div');
      sectionDiv.className = 'profile-data-section shadow rounded-md p-3'; 
      sectionDiv.style.backgroundColor = 'var(--ai-message-bg)';

      const titleEl = document.createElement('h4');
      titleEl.className = 'text-md font-semibold mb-2 border-b pb-1'; 
      titleEl.style.color = 'var(--text-color)'; // White text for title
      titleEl.style.borderColor = 'rgba(255, 255, 255, 0.2)'; // Lighter border for dark bg
      titleEl.textContent = sectionTitle;
      sectionDiv.appendChild(titleEl);

      const ul = document.createElement('ul');
      ul.className = 'space-y-1 text-base';

      for (const key in sectionData) {
        const li = document.createElement('li');
        li.className = 'flex justify-between items-center'; 

        const keySpan = document.createElement('span');
        keySpan.className = 'font-medium text-slate-600 mr-2'; // Added margin for spacing
        keySpan.style.color = 'var(--profile-card-key-text-color)';
        keySpan.textContent = `${key}:`;
        
        const valueSpan = document.createElement('span');
        valueSpan.className = 'text-slate-800 text-right break-all'; // Allow long values to break
        valueSpan.style.color = 'var(--profile-card-text-color)'; 
        valueSpan.textContent = sectionData[key] !== null && sectionData[key] !== undefined ? String(sectionData[key]) : 'N/A';
        
        li.appendChild(keySpan);
        li.appendChild(valueSpan);
        ul.appendChild(li);
      }
      sectionDiv.appendChild(ul);
      profileContainer.appendChild(sectionDiv);
    }
  }
  elements.profileSection.appendChild(profileContainer);
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
  adjustMessageContainerHeight,
  showChatScreen,
  updateProfileDisplay
};

// Allow other modules to update these states
