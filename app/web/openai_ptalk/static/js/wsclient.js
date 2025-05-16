// WebSocket Module - Handles communication with the server
import { debug, createMessageBubble, scrollToBottom, connectionState, updateConnectionUI, elements} from './ui.js';
import { playAudioChunk, stopAudioCapture, } from './audio.js';

// WebSocket state
let ws;
let wsConnected = false;
let connectionTimeout = null;
let userInitiatedDisconnect = false;

// SpeechBubble state
let userTranscriptFinalized = true;
let aiResponseBuffer = null;
let currentUserSpeechBubble = null;
let lastAiElem = null;



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
  if (!userTranscriptFinalized) {
    // Buffer AI response if user transcript isn't done yet
    debug("Buffering AI text delta (user transcript pending).");
    if (aiResponseBuffer === null) {
      // Start buffering
      aiResponseBuffer = { content: data.content || "", done: false };
      debug(`Initialized aiResponseBuffer: ${JSON.stringify(aiResponseBuffer)}`);
    } else {
      // Append to existing buffer
      aiResponseBuffer.content += data.content || "";
      debug(`Appended to aiResponseBuffer: ${JSON.stringify(aiResponseBuffer)}`);
    }
  } else {
    // User transcript is done (or we are before user speaks), display AI response immediately
    debug("Processing AI text delta (user transcript finalized or pre-speech).");
    if (lastAiElem === null) {
      debug("Creating new AI bubble. lastAiElem was null.");
      lastAiElem = createMessageBubble("ai", "AI: ");
      // Add buffered content (if any) + current delta
      let initialContent = "";
      if (aiResponseBuffer !== null) {
        debug(`Prepending buffered AI content: ${aiResponseBuffer.content}`);
        initialContent += aiResponseBuffer.content;
      }
      initialContent += data.content || "";
      lastAiElem.textContent += initialContent;
      // If buffer existed and was processed, clear it now
      if (aiResponseBuffer !== null) {
        debug("Clearing aiResponseBuffer after prepending.");
        aiResponseBuffer = null;
      }
    } else {
      // Append the current delta to existing bubble
      debug(`Appending delta "${data.content || ''}" to existing AI bubble.`);
      if (data.content) {
        lastAiElem.textContent += data.content;
      }
    }
    scrollToBottom();
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
}


// Handle audio chunk messages
function handleAudioChunk(data) {
  playAudioChunk(data.audio);
}


// Handle transcript delta messages
function handleTranscriptDelta(data) {
  debug(`>>> handleTranscriptDelta received: ${data.content}`);
  // Simplified logic
  if (currentUserSpeechBubble === null) {
    debug("Creating user speech bubble for first transcript delta.");
    // Initialize with the first delta content directly
    currentUserSpeechBubble = createMessageBubble("user", "You: " + (data.content || ""));
  } else {
    // Append subsequent deltas
    debug(`Appending transcript delta "${data.content || ''}" to user bubble.`);
    if (data.content) { // Ensure content exists before appending
      currentUserSpeechBubble.textContent += data.content;
    }
  }
  scrollToBottom();
}


// Handle transcript done messages
function handleTranscriptDone(data) {
  debug("Received input_audio_transcript_done. Finalizing user transcript.");
  currentUserSpeechBubble = null; // Release focus from user bubble

  let wasBufferProcessed = false;
  // Process any buffered AI content immediately
  if (aiResponseBuffer !== null) {
    debug(`Processing buffered AI content: ${JSON.stringify(aiResponseBuffer)}`);
    if (aiResponseBuffer.content) { // Only create bubble if there's content
      if (lastAiElem === null) {
        debug("Creating new AI bubble for buffered content in handleTranscriptDone.");
        lastAiElem = createMessageBubble("ai", "AI: ");
      }
      // Append the entire buffer content
      debug(`Appending buffered content "${aiResponseBuffer.content}" to AI bubble.`);
      lastAiElem.textContent += aiResponseBuffer.content;
      scrollToBottom();
    }
    wasBufferProcessed = true;
  }

  // Now mark transcript as finalized *after* potentially processing buffer
  userTranscriptFinalized = true;
  debug(`userTranscriptFinalized set to TRUE.`);

  // Check if the AI text stream had already finished (buffer marked as done)
  if (wasBufferProcessed && aiResponseBuffer.done) {
    debug("Buffered content was processed and marked as done. Resetting lastAiElem.");
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
  ws.send(JSON.stringify({ type: "user_message", text }));
  return true;
}

function setCurrentUserSpeechBubble(bubble) {
  currentUserSpeechBubble = bubble;
}

function setLastAiElem(elem) {
  lastAiElem = elem;
}


//-------------------------------------------------
// Handle client WebSocket messages
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

// Export public API
export {
  wsConnected,
  ws,
  connect,
  disconnect,
  sendTextMessage,
  isConnected,
  getWebSocket
};