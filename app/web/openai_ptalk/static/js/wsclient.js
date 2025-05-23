// WebSocket Module - Handles communication with the server
import {
  debug, 
  createMessageBubble,
  updateMessageBubbleContent,
  scrollToBottom, 
  connectionState, 
  updateConnectionUI, 
  elements, 
  updateProfileDisplay,
  updateNutritionTrackingDisplay,
  displayTakeawayRecommendations,
  updateWeeklyReviewDisplay
} from './ui.js';
import { playAudioChunk, stopAudioCapture, } from './audio.js';

// WebSocket state
let ws;
let wsConnected = false;

// SpeechBubble state
let userTranscriptFinalized = true;
let aiResponseBuffer = null;
let currentUserSpeechBubble = null;
let lastAiElem = null;

// withhold some payload until transcript is finalized
let pendingTakeawayPayload = null



//-------------------------------------------------
// Manage WebSocket connections
//-------------------------------------------------

// Check if WebSocket is connected
function isConnected() {
  return wsConnected && ws && ws.readyState === window.WebSocket.OPEN;
}

// Get WebSocket instance
function getWebSocket() {
  return ws;
}

// Connect to WebSocket server
function connect() {
  if (isConnected()) {
    debug("WebSocket already connected");
    return;
  }
  
  updateConnectionUI("CONNECTING");
  
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
  
  // Set up WebSocket event handlers
  ws.onopen = () => {
    wsConnected = true;
    debug("WebSocket connection opened");
    updateConnectionUI("CONNECTED");
  };
  
  ws.onclose = (event) => {
    wsConnected = false;
    debug(`WebSocket connection closed: ${event.code} ${event.reason}`);
    updateConnectionUI("DISCONNECTED");
    stopAudioCapture();
  };
  
  ws.onerror = (error) => {
    debug(`WebSocket error: ${error}`);
    updateConnectionUI("DISCONNECTED");
  };
  
  ws.onmessage = handleWebSocketMessage;
}

// Disconnect WebSocket
function disconnect() {
  if (!ws) return;
  
  stopAudioCapture();
  ws.close();
  ws = null;
  wsConnected = false;
  updateConnectionUI("DISCONNECTED");
}


//-------------------------------------------------
// Handle incoming WebSocket messages
//-------------------------------------------------
function handleWebSocketMessage(e) {
  try {
    const data = JSON.parse(e.data);
    debug(`Received WS message: Type: ${data.type}`);

    switch (data.type) {
      case "text_delta":              handleTextDelta(data); break;
      case "text_done":               handleTextDone(data); break;
      case "audio_chunk":             handleAudioChunk(data); break;
      case "input_audio_transcript_delta": handleTranscriptDelta(data); break;
      case "input_audio_transcript_done": handleTranscriptDone(data); break;
      case "input_audio_buffer_committed": handleInputBufferCommitted(data); break;
      case "profile_update":          updateProfileDisplay(data); break;
      case "nutrition_tracking_update": updateNutritionTrackingDisplay(data); break;
      case "takeaway_recommendation": handleTakeawayRecommendation(data); break;
      case "weekly_review_data":      updateWeeklyReviewDisplay(data); break; 
      case "error":                   handleServerError(data); break;
      default:
        // Log other potentially useful events if needed, but less verbosely
        if (!["session.created", "input_audio_buffer.speech_started", "input_audio_buffer.speech_stopped", "conversation.item.created", "rate_limits.updated", "response.created", "response.output_item.added", "response.output_item.done", "response.content_part.added", "response.content_part.done", "response.audio.done", "response.done"].includes(data.type)) {
          debug(`Unhandled/Info message type: ${data.type}`);
        }
    }
  } catch (err) {
    console.error(`Error handling WebSocket message: ${err.message}`, e.data);
    debug(`Error handling message: ${err.message}`);
    resetStateAfterError(`Message processing error: ${err.message}`);
  }
}


// Handle text delta messages
function handleTextDelta(data) {
  debug(`>>> handleTextDelta received: ${data.content}. userTranscriptFinalized=${userTranscriptFinalized}`);
  const newRawTextChunk = data.content || "";

  if (!userTranscriptFinalized) {
    // Buffer AI response if user transcript isn't done yet
    debug("Buffering AI text delta (user transcript pending).");
    if (aiResponseBuffer === null) {
      // Start buffering
      aiResponseBuffer = { content: newRawTextChunk, done: false };
      debug(`Initialized aiResponseBuffer: ${JSON.stringify(aiResponseBuffer)}`);
    } else {
      // Append to existing buffer
      aiResponseBuffer.content += newRawTextChunk;
      debug(`Appended to aiResponseBuffer: ${JSON.stringify(aiResponseBuffer)}`);
    }
  } else {
    // User transcript is done (or we are before user speaks), display AI response immediately
    debug("Processing AI text delta (user transcript finalized or pre-speech).");
    if (lastAiElem === null) {
      debug("Creating new AI bubble. lastAiElem was null.");
      let fullInitialRawText = ""; // Using "Al: " from your image
      if (aiResponseBuffer !== null) {
        debug(`Prepending buffered AI content: ${aiResponseBuffer.content}`);
        fullInitialRawText += aiResponseBuffer.content;
        // Clear buffer AFTER using its content for the initial bubble
        debug("Clearing aiResponseBuffer after prepending for new bubble.");
        aiResponseBuffer = null; 
      }
      fullInitialRawText += newRawTextChunk;
      lastAiElem = createMessageBubble("ai", fullInitialRawText); 
    } else {
      // Append the current delta to existing bubble
      debug(`Updating existing AI bubble with delta: "${newRawTextChunk}"`);
      updateMessageBubbleContent(lastAiElem, newRawTextChunk);
    }
  }
}


// Handle text done messages
function handleTextDone(data) {
  debug(`AI text stream finished (text_done). userTranscriptFinalized=${userTranscriptFinalized}`);

  if (userTranscriptFinalized) {
    // Transcript already done, AI text finished, so turn is complete.
    debug("Resetting lastAiElem because transcript is finalized and text_done received.");
    lastAiElem = null; // Reset AI bubble reference for the next turn
    // Ensure buffer is clear if it somehow existed
    if (aiResponseBuffer !== null) {
      debug("Clearing lingering aiResponseBuffer in handleTextDone.");
      aiResponseBuffer = null;
    }
  } else {
    // Transcript not done yet, but AI text is. Mark buffer as done.
    if (aiResponseBuffer !== null) {
      aiResponseBuffer.done = true;
      debug(`Marked aiResponseBuffer as done: ${JSON.stringify(aiResponseBuffer)}`);
    } else {
      // This case (text_done before text_delta during buffering) is unlikely but possible
      // Create a buffer marked as done but with empty content
      aiResponseBuffer = { content: "", done: true };
      debug(`Received text_done before text_delta while buffering. Initialized buffer as done: ${JSON.stringify(aiResponseBuffer)}`);
    }
  }

  // Display pending takeaway recommendations now that the AI text is complete
  if (pendingTakeawayPayload) {
    debug("Processing pending takeaway recommendations after AI text_done.");
    // displayTakeawayRecommendations in ui.js creates its own new AI message bubble.
    // This is fine as lastAiElem has been reset if the turn was fully processed.
    displayTakeawayRecommendations(pendingTakeawayPayload);
    pendingTakeawayPayload = null; // Clear after displaying
  }
}


// Handle audio chunk messages
function handleAudioChunk(data) {
  playAudioChunk(data.audio);
}


// Handle transcript delta messages
function handleTranscriptDelta(data) {
  debug(`>>> handleTranscriptDelta received: ${data.content}`);
  const newRawTextChunk = data.content || "";

  if (currentUserSpeechBubble === null) {
    debug("Creating user speech bubble for first transcript delta.");
    // Initialize with the first delta content directly
    currentUserSpeechBubble = createMessageBubble("user", newRawTextChunk);
  } else {
    // Append subsequent deltas
    debug(`Updating existing user bubble with transcript delta: "${newRawTextChunk}"`);
    updateMessageBubbleContent(currentUserSpeechBubble, newRawTextChunk);
  }
}


// Handle transcript done messages
function handleTranscriptDone(data) {
  debug("Received input_audio_transcript_done. Finalizing user transcript.");
  currentUserSpeechBubble = null; // Release focus from user bubble

  let wasBufferProcessed = false; // This variable is from your existing logic
  // Process any buffered AI content immediately
  if (aiResponseBuffer !== null) {
    debug(`Processing buffered AI content: ${JSON.stringify(aiResponseBuffer)}`);
    if (aiResponseBuffer.content) { // Only process if there's content
      const bufferedAIRawContent = aiResponseBuffer.content;
      if (lastAiElem === null) {
        debug("Creating new AI bubble for buffered content in handleTranscriptDone.");
        lastAiElem = createMessageBubble("ai", bufferedAIRawContent); // Using "Al: "
      } else {
        // If lastAiElem exists, it means some part of AI response might have already streamed.
        // Append the rest of the buffered content.
        debug(`Updating existing AI bubble with buffered content: "${bufferedAIRawContent}"`);
        updateMessageBubbleContent(lastAiElem, bufferedAIRawContent);
      }
      // scrollToBottom(); // createMessageBubble and updateMessageBubbleContent in ui.js now handle this
    }
    wasBufferProcessed = true;
  }

  // Now mark transcript as finalized *after* potentially processing buffer
  userTranscriptFinalized = true;
  debug(`userTranscriptFinalized set to TRUE.`);

  // Check if the AI text stream had already finished (buffer marked as done)
  if (wasBufferProcessed && aiResponseBuffer && aiResponseBuffer.done) {
    debug("Buffered content was processed and AI stream was already done. Resetting lastAiElem.");
    lastAiElem = null; // Reset AI bubble, turn is complete
  }

  // Clear the buffer now that transcript is done and buffer (if any) was handled
  if (aiResponseBuffer !== null) {
    debug("Clearing aiResponseBuffer in handleTranscriptDone.");
    aiResponseBuffer = null;
  }
}


// Handle input buffer committed messages
function handleInputBufferCommitted(data) {
  debug("Received input_audio_buffer_committed. Resetting flags for new turn.");
  userTranscriptFinalized = false;
  
  // Clear any potentially lingering buffer from an incomplete previous turn
  if (aiResponseBuffer !== null) {
    debug("Clearing aiResponseBuffer in handleInputBufferCommitted.");
    aiResponseBuffer = null;
  }

  debug(`userTranscriptFinalized set to FALSE.`);
}


// Handle server error messages
function handleServerError(data) {
  const errorMsg = data.message || "Unknown server error";
  console.error(`WebSocket error message from server: ${errorMsg}`);
  debug(`Received error message: ${errorMsg}`);
  resetStateAfterError(`Server error: ${errorMsg}`);
}


// Send a text message to the server
function sendTextMessage(text) {
  if (!text || !isConnected()) {
    debug(`Cannot send text: wsConnected=${wsConnected}, ws.readyState=${ws?.readyState}`);
    return false;
  }

  debug(`Sending text message: ${text}`);

  // Send JSON over WebSocket
  const message = {
    type: "user_text_message",
    payload: {
      text: text
    }
  };
  ws.send(JSON.stringify(message));
  return true;
}

// Handle takeaway recommendation messages
function handleTakeawayRecommendation(data) {
  debug("Received takeaway recommendation from server.");
  if (data.payload && data.payload.recommendations) { // Ensure recommendations exist
    debug("Buffering takeaway recommendations.");
    pendingTakeawayPayload = data.payload; // Buffer the payload
    // Do NOT call displayTakeawayRecommendations here
  } else {
    debug("Takeaway recommendation payload is missing, invalid, or has no recommendations.");
    pendingTakeawayPayload = null; // Clear any old pending payload if this one is invalid
  }
}

//-------------------------------------------------
// Handle client UI Buttons and Events
//-------------------------------------------------

// Handle send button click
function handleSendButtonClick() {
  const text = elements.inputEl.value.trim();
  if (!text) return;
  
  if (sendTextMessage(text)) {
    // Message sent successfully
    createMessageBubble("user", "You: " + text);
    elements.inputEl.value = "";
    elements.inputEl.focus();
    scrollToBottom();
  }
}

// send photo file names for nutrition estimation
function sendMealPhotoForEstimation(fileNamesArray) {
  if (!isConnected()) {
    debug("Cannot send photo names: WebSocket not connected.");
    // showSystemMessage("Cannot estimate photos: Not connected.", "error"); // If you have showSystemMessage
    console.error("Cannot estimate photos: Not connected.");
    if (elements.estimatePhotosBtn) { // Re-enable button if called when not connected
        elements.estimatePhotosBtn.disabled = false;
        elements.estimatePhotosBtn.textContent = 'Estimate Nutrition';
    }
    return false;
  }
  if (!fileNamesArray || fileNamesArray.length === 0) {
    debug("Cannot send photo names: No file names provided.");
    // The calling logic in main.js should handle UI if no files are selected
    return false;
  }

  const message = {
    type: "estimate_photos_nutrition", // Changed type
    payload: {
      filenames: fileNamesArray, 
    },
  };
  ws.send(JSON.stringify(message));
  debug("Sent photo names for estimation:", message);
  return true; 
}


function requestWeeklyReviewData() {
  if (!isConnected()) {
    debug("Cannot request weekly review: WebSocket not connected.");
    // Optionally, show an error to the user or disable the button if not connected
    // For now, just log and return false
    if (elements.loadWeeklyReviewBtn) { // Attempt to re-enable if it was disabled
        elements.loadWeeklyReviewBtn.disabled = false;
        elements.loadWeeklyReviewBtn.textContent = 'Review Last 7 Days';
    }
    return false;
  }

  const message = {
    type: "request_weekly_review"
  };
  ws.send(JSON.stringify(message));
  debug("Sent request_weekly_review to backend.");
  return true;
}


// Export public API
export {
  wsConnected,
  ws,
  connect,
  disconnect,
  sendTextMessage,
  sendMealPhotoForEstimation,
  requestWeeklyReviewData,
  isConnected,
  getWebSocket
};