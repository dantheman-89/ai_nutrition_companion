// UI Module - Handles DOM interactions and UI updates

// Cache DOM elements
const elements = {
  // Startup screen elements
  startupScreen: document.getElementById('startup-screen'),
  startupCircle: document.getElementById('startup-circle'),
  startupText: document.getElementById('startup-text'),
  // Main app container
  appContainer: document.getElementById('app-container'),
  // Left Section - Messaging & input control elements
  messagesSection: document.getElementById("messages"), // chat message section
  connectBtn: document.getElementById("connect"), // connect button at the bottom
  inputEl: document.getElementById("input"), // text input bar at the bottom
  sendBtn: document.getElementById("send"), // text send buttons at the bottom
  recordBtn: document.getElementById("record"), // record button at the bottom
  // Right Section - Info panel elements
  infoPanelsSection: document.getElementById('info-panels-section'), 
  // Profile Panel elements
  profileContentArea: document.getElementById('profile-content-area'),
  // Nutrition Tracking Panel Elements
  nutritionTrackingContentArea: document.getElementById('nutrition-tracking-content-area'), // Content area for 2nd panel
  energyQuotaCardContainer: document.getElementById('energy-quota-card-container'),
  nutritionProgressCardContainer: document.getElementById('nutrition-progress-card-container'),
  uploadMealCard: document.getElementById('upload-meal-card'),
  uploadPhotoTriggerBtn: document.getElementById('upload-photo-trigger-btn'),
  mealPhotoInput: document.getElementById('mealPhotoInput'),
  selectedFilesCount: document.getElementById('selected-files-count'),
  estimatePhotosBtn: document.getElementById('estimate-photos-btn'),
  processedMealPhotosContainer: document.getElementById('processed-meal-photos-container'),
  // debugging elements
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
  updateProfileDisplay({ data: {} });
  updateNutritionTrackingDisplay({});
  // showChatScreen(); // Debug code, remove this line in production
  
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

// Text Formatting Helper
function formatTextForHTML(text) {
  if (typeof text !== 'string') {
    return '';
  }
  // First, replace newlines with <br>, then process bold markdown.
  // This order ensures that **text\nwithbold** becomes <strong>text<br>withbold</strong>.
  return text
    .replace(/\n/g, '<br>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
}

// Create a new message bubble in the chat
// Create a new message bubble in the chat
function createMessageBubble(sender, initialText) {
  const bubbleDiv = document.createElement("div");

  // Store the raw initial text
  bubbleDiv.dataset.rawText = initialText;
  // Use the formatter and set innerHTML
  bubbleDiv.innerHTML = formatTextForHTML(initialText);
  
  if (sender === "user") {
    bubbleDiv.className = "message-bubble user-message";
  } else { // AI
    bubbleDiv.className = "message-bubble ai-message";
  }
  elements.messagesSection.appendChild(bubbleDiv);
  scrollToBottom();
  return bubbleDiv;
}

// New function to update existing message bubble content
function updateMessageBubbleContent(bubbleElement, newRawTextChunk) {
  if (!bubbleElement) return;

  // Retrieve current raw text, append new chunk
  let currentRawText = bubbleElement.dataset.rawText || "";
  currentRawText += newRawTextChunk;
  
  // Store updated raw text
  bubbleElement.dataset.rawText = currentRawText;
  
  // Re-render the entire bubble content with formatting
  bubbleElement.innerHTML = formatTextForHTML(currentRawText);
  scrollToBottom(); // Ensure visibility
}

function scrollToBottom() {
  elements.messagesSection.scrollTop = elements.messagesSection.scrollHeight;
}


// --- Display Takeaway Recommendations ---
function displayTakeawayRecommendations(payload) {
  debug("Displaying takeaway recommendations");
  if (!payload || !payload.recommendations || payload.recommendations.length === 0) {
    debug("No takeaway recommendations to display or payload is invalid.");
    return;
  }

  const aiBubble = createMessageBubble("ai", ""); // Create an empty AI bubble

  // Add summary text if provided
  if (payload.summary_text) {
    const summaryP = document.createElement('p');
    summaryP.textContent = payload.summary_text;
    summaryP.style.marginBottom = '10px'; // Add some spacing
    aiBubble.appendChild(summaryP);
  }

  const recommendationsContainer = document.createElement('div');
  recommendationsContainer.className = 'takeaway-recommendations-container';

  payload.recommendations.forEach(rec => {
    const card = document.createElement('div');
    card.className = 'takeaway-recommendation-card';

    let nutritionHtml = '';
    if (rec.nutrition) {
      const nutritionItems = [
        { key: 'Kilojoules:', value: rec.nutrition.kilojoules !== undefined ? rec.nutrition.kilojoules.toLocaleString() : 'N/A' },
        { key: 'Protein:', value: rec.nutrition.protein_grams !== undefined ? `${rec.nutrition.protein_grams}g` : 'N/A' },
        { key: 'Fat:', value: rec.nutrition.fat_grams !== undefined ? `${rec.nutrition.fat_grams}g` : 'N/A' },
        { key: 'Carbs:', value: rec.nutrition.carbohydrate_grams !== undefined ? `${rec.nutrition.carbohydrate_grams}g` : 'N/A' },
        { key: 'Fiber:', value: rec.nutrition.fiber_grams !== undefined ? `${rec.nutrition.fiber_grams}g` : 'N/A' }
      ];
      nutritionHtml = `
        <ul class="nutrition-details">
          ${nutritionItems.map(item => `<li><span class="key">${item.key}</span><span class="value">${item.value}</span></li>`).join('')}
        </ul>
      `;
    }

   let storeHtml = ''; // This variable holds the correct store HTML with the link
    if (rec.store) {
      if (rec.store_url) {
        storeHtml = `<p class="takeaway-store">Order link: <a href="${rec.store_url}" target="_blank" rel="noopener noreferrer" class="store-link">${rec.store}</a></p>`;
      } else {
        storeHtml = `<p class="takeaway-store">Store: ${rec.store}</p>`;
      }
    }
    
    card.innerHTML = `
      ${rec.image_url ? `<img src="${rec.image_url}" alt="${rec.description || 'Takeaway option'}" class="takeaway-image">` : ''}
      <div class="takeaway-info">
        <h4 class="takeaway-description">${rec.description || 'Takeaway Option'}</h4>
        ${storeHtml}
        ${nutritionHtml}
      </div>
    `;
    recommendationsContainer.appendChild(card);
  });

  aiBubble.appendChild(recommendationsContainer);
  scrollToBottom(); // Ensure the new content is visible
}

// ---------------------------------------------------------
// Right handside info panel elements 
// ---------------------------------------------------------
function initializeCollapsiblePanels() {
  const panelHeaders = document.querySelectorAll('#info-panels-section .collapsible-panel .panel-header');
  panelHeaders.forEach(header => {
    header.addEventListener('click', () => {
      const panel = header.closest('.collapsible-panel');
      const content = panel.querySelector('.panel-content');
      
      // Close all other open panels in the same section
      document.querySelectorAll('#info-panels-section .collapsible-panel .panel-content.open').forEach(openContent => {
        if (openContent !== content) {
          openContent.classList.remove('open');
          const otherHeader = openContent.previousElementSibling;
          if (otherHeader) {
            otherHeader.classList.remove('active');
          }
        }
      });

      // Toggle current panel
      const isOpen = content.classList.toggle('open');
      header.classList.toggle('active', isOpen);
    });
  });

  // Optional: Ensure the first panel (User Profile) is open by default and styled correctly
  const firstPanel = document.querySelector('#info-panels-section .collapsible-panel');
  if (firstPanel) {
      const firstHeader = firstPanel.querySelector('.panel-header');
      const firstContent = firstPanel.querySelector('.panel-content');
      if (firstHeader && firstContent && firstContent.classList.contains('open')) {
          firstHeader.classList.add('active');
      }
  }
}


// --- Update "User Profile" Panel (First Panel) ---
function updateProfileDisplay(msg) {
  const profileDataForDisplay = msg && msg.data ? msg.data : {};

  if (!elements.profileContentArea) {
    debug("Profile content area element not found for User Profile panel.");
    return;
  }

  if (!profileDataForDisplay || Object.keys(profileDataForDisplay).length === 0) {
    // Inject only the placeholder paragraph.
    // The parent .panel-content.open provides the "card-like" padding.
    elements.profileContentArea.innerHTML = `
        <p class="placeholder-text">Profile information will be displayed here once available.</p>
      `;
    debug("Profile data for display is empty, showing placeholder in User Profile panel.");
  } else {
    debug("Updating User Profile panel display with new data.");
    let profileHtml = '';
    for (const sectionTitle in profileDataForDisplay) {
      if (Object.hasOwnProperty.call(profileDataForDisplay, sectionTitle)) {
        const sectionData = profileDataForDisplay[sectionTitle];
        if (typeof sectionData === 'object' && sectionData !== null && Object.keys(sectionData).length > 0) {
          profileHtml += `<div class="profile-data-section"><h4>${sectionTitle}</h4><ul>`;
          for (const key in sectionData) {
            if (Object.hasOwnProperty.call(sectionData, key)) {
              profileHtml += `<li><span class="profile-key">${key}:</span> <span class="profile-value">${sectionData[key] !== null && sectionData[key] !== undefined ? String(sectionData[key]) : 'N/A'}</span></li>`;
            }
          }
          profileHtml += `</ul></div>`;
        }
      }
    }
    // When profile data is available, it uses .profile-data-section which has its own card styling.
    elements.profileContentArea.innerHTML = profileHtml || '<p class="placeholder-text">No details to display.</p>';
  }
}

// --- Central Function to Update "Nutrition Tracking" Panel (Second Panel) ---
function updateNutritionTrackingDisplay(msg) {
  debug("Updating Nutrition Tracking panel with data");

  // load message data
    const trackingData = msg && msg.data ? msg.data : {};

  // --- 1. Update "Daily Energy Quota" Card ---
  if (elements.energyQuotaCardContainer) {
    elements.energyQuotaCardContainer.innerHTML = ''; // Clear previous content
    const quotaTitle = document.createElement('h4');
    quotaTitle.className = 'card-title';
    quotaTitle.textContent = 'Daily Energy Quota';
    elements.energyQuotaCardContainer.appendChild(quotaTitle);

    const energyQuotaData = trackingData["Daily Energy Quota"] || {};

    if (Object.keys(energyQuotaData).length > 0) {
        for (const key in energyQuotaData) {
            if (Object.hasOwnProperty.call(energyQuotaData, key)) {
                const p = document.createElement('p');
                // Add 'text-xs' class for "Baseline" and "Exercise" for consistency if desired
                if (key === "Baseline" || key === "Exercise") {
                    p.className = 'text-xs';
                }
                p.innerHTML = `${key}: <span>${energyQuotaData[key]}</span>`; // Value already formatted with unit
                elements.energyQuotaCardContainer.appendChild(p);
            }
        }
    } else {
      elements.energyQuotaCardContainer.appendChild(document.createTextNode("No energy quota data available."));
    }
  } else {
    debug("Energy quota card container not found.");
  }

  // --- 2. Update "Daily Tracking" Card ---
  if (elements.nutritionProgressCardContainer) {
    elements.nutritionProgressCardContainer.innerHTML = ''; // Clear previous content
    const progressTitle = document.createElement('h4');
    progressTitle.className = 'card-title';
    progressTitle.textContent = 'Daily Tracking';
    elements.nutritionProgressCardContainer.appendChild(progressTitle);

    const dailyTrackingData = trackingData["Daily Tracking"] || {};

    if (dailyTrackingData["Energy"]) {
      const energyData = dailyTrackingData["Energy"];
      const energyP = document.createElement('p');
      energyP.innerHTML = `Energy: <span>${energyData.consumed || '0'}</span> / <span>${energyData.target || '0'}</span> ${energyData.unit || 'kJ'}`;
      elements.nutritionProgressCardContainer.appendChild(energyP);

      const progressBarContainer = document.createElement('div');
      progressBarContainer.className = 'progress-bar-container my-1'; // Ensure 'my-1' or similar margin utility if from Tailwind, or add margin in CSS
      const progressBar = document.createElement('div');
      progressBar.className = 'progress-bar';
      
      const consumed = parseFloat(String(energyData.consumed).replace(/,/g, '')) || 0; // Ensure parsing after removing commas
      const target = parseFloat(String(energyData.target).replace(/,/g, '')) || 0; // Ensure parsing after removing commas
      let percentage = 0;
      if (target > 0) {
        percentage = (consumed / target) * 100;
      } else if (consumed > 0) { // Consumed but no target, consider 100% or a specific state
        percentage = 100; 
      }

      if (consumed > target && target > 0) { // Over quota
        progressBar.style.width = '100%';
        progressBar.style.backgroundColor = 'var(--over-quota-red)';
        // You could add text inside the bar if it's wide enough, or a tooltip
        // progressBar.textContent = `Over by ${Math.round(consumed - target)}${energyData.unit || 'kJ'}`;
      } else { // Under or at quota
        progressBar.style.width = `${Math.min(percentage, 100)}%`;
        progressBar.style.backgroundColor = 'var(--record-green)';
      }
      progressBarContainer.appendChild(progressBar);
      elements.nutritionProgressCardContainer.appendChild(progressBarContainer);
    }

    const macrosOrder = ["Protein", "Fat", "Carbs", "Fiber"]; // Define order
    const macrosContainer = document.createElement('div');
    macrosContainer.className = 'macros-display-container'; // New class for styling
    let hasMacros = false;
    macrosOrder.forEach(macroName => {
        if (dailyTrackingData[macroName]) {
            hasMacros = true;
            const macroData = dailyTrackingData[macroName];
            const macroSpan = document.createElement('span');
            macroSpan.className = 'macro-item'; // New class for styling individual items
            
            let macroText = `${macroName}: `;
            if (macroData.consumed_g !== undefined && macroData.target_g !== undefined) {
                macroText += `${macroData.consumed_g || '0'}/${macroData.target_g || '0'}g`;
                if (macroData.percentage !== undefined) {
                    macroText += ` (${macroData.percentage || 0}%)`;
                }
            } else if (macroData.percentage !== undefined) { // Fallback if only percentage is available
                macroText += `${macroData.percentage || 0}%`;
            } else {
                macroText += 'N/A'; // Fallback if no data
            }
            macroSpan.textContent = macroText;
            macrosContainer.appendChild(macroSpan);
        }
    });

    if (hasMacros) {
        elements.nutritionProgressCardContainer.appendChild(macrosContainer);
    }

     if (Object.keys(dailyTrackingData).length === 0 && !dailyTrackingData["Energy"]) { // Check if truly empty
      const noDataP = document.createElement('p');
      noDataP.textContent = "No daily tracking data available.";
      elements.nutritionProgressCardContainer.appendChild(noDataP);
    }

  } else {
    debug("Nutrition progress card container element not found.");
  }

  // --- 3. Update "Processed Meal Photos" ---
  // This part assumes trackingData might also contain "Logged Meals" or similar
  // It reuses the existing displayProcessedMealResults logic but calls it with the relevant part of trackingData.
  if (elements.processedMealPhotosContainer) {
    const loggedMealsData = trackingData["Logged Meals"] || []; // Expect an array
    // We can call the existing displayProcessedMealResults directly if its input matches
    // For this refactor, let's assume displayProcessedMealResults expects an object like { processed_photos: [...] }
    displayProcessedMealResults({ processed_photos: loggedMealsData });
  } else {
    debug("Processed meal photos container not found.");
  }
}

// --- Meal Photo Upload UI Logic (setupPhotoUploadLogic) ---
// This function remains largely the same as it sets up event listeners for existing HTML elements
function setupPhotoUploadLogic() {
  if (elements.uploadPhotoTriggerBtn && elements.mealPhotoInput && elements.estimatePhotosBtn && elements.selectedFilesCount) {
    elements.uploadPhotoTriggerBtn.addEventListener('click', () => elements.mealPhotoInput.click());
    elements.mealPhotoInput.addEventListener('change', (event) => {
      if (event.target.files && event.target.files.length > 0) {
        elements.selectedFilesCount.textContent = `${event.target.files.length} photo(s) selected`;
        elements.estimatePhotosBtn.classList.remove('hidden');
      } else {
        elements.selectedFilesCount.textContent = 'No photos selected';
        elements.estimatePhotosBtn.classList.add('hidden');
      }
    });
  }
}

// --- Display Processed Meal Photos (Can be called by updateNutritionTrackingDisplay) ---
function displayProcessedMealResults(data) { // data is expected to be { processed_photos: [...] }
  if (!elements.processedMealPhotosContainer) {
    debug("Processed meal photos container not found.");
    return;
  }
  elements.processedMealPhotosContainer.innerHTML = ''; 

  const photos = data.processed_photos || [];

  if (photos.length > 0) {
    photos.forEach(meal => { 
      const card = document.createElement('div');
      card.className = 'processed-meal-card';
      
      let itemsHtml = '';
      if (meal.items && typeof meal.items === 'object' && Object.keys(meal.items).length > 0) {
        itemsHtml = Object.entries(meal.items).map(([itemName, itemNutrition]) => `
          <div class="item-entry">
            <span class="item-name">${itemName}</span>
            <span class="item-kj">${itemNutrition.kilojoules !== undefined ? itemNutrition.kilojoules.toLocaleString() : '0'} kJ</span>
          </div>
        `).join('');
      }
      
      const totalMealKj = meal.nutrition && meal.nutrition.kilojoules !== undefined ? meal.nutrition.kilojoules : 0;
      const protein = meal.nutrition && meal.nutrition.protein_grams !== undefined ? meal.nutrition.protein_grams : 0;
      const fat = meal.nutrition && meal.nutrition.fat_grams !== undefined ? meal.nutrition.fat_grams : 0;
      const carbs = meal.nutrition && meal.nutrition.carbohydrate_grams !== undefined ? meal.nutrition.carbohydrate_grams : 0;
      const fiber = meal.nutrition && meal.nutrition.fiber_grams !== undefined ? meal.nutrition.fiber_grams : 0;

      // Build macros HTML for flex display
      let macrosHtml = '';
      if (meal.nutrition) { // Check if nutrition object exists
        macrosHtml += `<div class="macro-item">Protein: <span>${protein}g</span></div>`;
        macrosHtml += `<div class="macro-item">Fat: <span>${fat}g</span></div>`;
        macrosHtml += `<div class="macro-item">Carbs: <span>${carbs}g</span></div>`;
        macrosHtml += `<div class="macro-item">Fiber: <span>${fiber}g</span></div>`;
      }


      card.innerHTML = `
        <h5 class="meal-title">${meal.description || 'Logged Meal'}</h5>
        ${meal.image_url ? `<img src="${meal.image_url}" alt="${meal.description || 'Meal'}" class="meal-image">` : ''}
        <div class="nutrition-summary">
          <div></div> ${/* Placeholder for potential left-aligned content */''}
          <div class="total-kj">${totalMealKj.toLocaleString()} kJ</div>
        </div>
        <div class="macros">
          ${macrosHtml}
        </div>
        ${itemsHtml ? `<h6 class="items-list-title">Items:</h6><div class="items-container">${itemsHtml}</div>` : ''}
      `;
      elements.processedMealPhotosContainer.appendChild(card);  
    });
    
  } else {
    // No need to add a placeholder here if it's desired to show nothing when empty
    // elements.processedMealPhotosContainer.innerHTML = '<p class="text-xs" style="color: var(--content-key-text-color);">No meal photo data to display.</p>';
  }

  // Re-enable the estimate photos button
  if (elements.estimatePhotosBtn) {
    elements.estimatePhotosBtn.disabled = false;
    elements.estimatePhotosBtn.textContent = 'Estimate Nutrition';
  };
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
  updateMessageBubbleContent,
  formatTextForHTML,
  debug,
  scrollToBottom,
  connectionState,
  adjustMessageContainerHeight,
  showChatScreen,
  initializeCollapsiblePanels,
  updateProfileDisplay,
  updateNutritionTrackingDisplay,
  displayProcessedMealResults,
  setupPhotoUploadLogic,
  displayTakeawayRecommendations
};

// Add these lines for console debugging:
// REMEMBER TO REMOVE THESE AFTER TESTING
if (DEBUG) { // Optional: only expose if DEBUG is true
    window.testUpdateProfile = updateProfileDisplay;
    window.testUpdateNutritionTracking = updateNutritionTrackingDisplay;
    window.testDisplayTakeawayRecommendations = displayTakeawayRecommendations;
    window.uiElements = elements; // Expose elements for inspection too
}