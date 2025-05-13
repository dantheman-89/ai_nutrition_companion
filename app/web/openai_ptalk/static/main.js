const messagesDiv = document.getElementById("messages");
const inputEl = document.getElementById("input");
const sendBtn = document.getElementById("send");
const recordBtn = document.getElementById("record"); 
const statusEl = document.getElementById("status");
const debugEl = document.getElementById("debug");

// --- Audio Playback ---
let audioContext;
let audioQueue = [];
let isPlaying = false;

function getAudioContext() {
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: 24000 // Match OpenAI's expected sample rate
    });
  }
  return audioContext;
}

// Convert base64 to ArrayBuffer
function base64ToArrayBuffer(base64) {
  try {
    const binaryString = atob(base64);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
      bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes.buffer;
  } catch (err) {
    console.error(`Base64 decoding error: ${err.message}`);
    return new ArrayBuffer(0);
  }
}

// Play audio chunk from base64
async function playAudioChunk(base64Audio) {
  try {
    if (!base64Audio) return;
    
    // Add to queue and start playing if not already
    audioQueue.push(base64Audio);
    if (!isPlaying) {
      playNextAudioChunk();
    }
  } catch (err) {
    console.error(`Error queuing audio: ${err.message}`);
  }
}

// Play next audio chunk from queue
async function playNextAudioChunk() {
  if (audioQueue.length === 0) {
    isPlaying = false;
    return;
  }
  
  isPlaying = true;
  const base64Audio = audioQueue.shift();
  
  try {
    const arrayBuffer = base64ToArrayBuffer(base64Audio);
    if (arrayBuffer.byteLength === 0) {
      playNextAudioChunk();
      return;
    }
    
    const ctx = getAudioContext();
    const audioBuffer = await ctx.decodeAudioData(arrayBuffer).catch(e => {
      console.error(`Audio decode error: ${e}`);
      return null;
    });
    
    if (!audioBuffer) {
      playNextAudioChunk();
      return;
    }
    
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);
    source.onended = playNextAudioChunk;
    source.start();
  } catch (err) {
    console.error(`Error playing audio: ${err.message}`);
    // Continue to next chunk even if there's an error
    playNextAudioChunk();
  }
}

// --- WebSocket & State Management ---
let ws;
let wsConnected = false;
let isAudioCaptureActive = false; // User intent: Are we trying to capture? (Button state)
let isRecording = false;       // Internal state: Is the audio processor actually running?
let currentUserSpeechBubble = null; // Current bubble for user speech deltas
let lastAiElem = null; // Current bubble for AI text deltas
let userTranscriptFinalized = true; // Start as TRUE
// Use null to indicate no active buffer, object otherwise
let aiResponseBuffer = null; // { content: string, done: boolean }

// Audio Capture Globals
let audioStream = null;
let sourceNode = null;
let audioWorkletNode = null;
let scriptProcessorNode = null;

// --- WebSocket Connection ---
function initWebSocket(onOpenCallback = null) {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    debug(`WebSocket already ${ws.readyState === WebSocket.OPEN ? 'open' : 'connecting'}.`);
    if (ws.readyState === WebSocket.OPEN && onOpenCallback) {
      onOpenCallback();
    }
    return;
  }
  debug("Initializing WebSocket connection...");
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

  ws.onopen = () => {
    wsConnected = true;
    setStatus("Connected");
    debug("WebSocket connection opened.");
    if (onOpenCallback) {
      onOpenCallback();
    }
  };

  ws.onclose = (event) => handleWebSocketDisconnectOrError('close', event);
  ws.onerror = (error) => handleWebSocketDisconnectOrError('error', error);
  ws.onmessage = handleWebSocketMessage; // Use dedicated handler function
}

function handleWebSocketDisconnectOrError(type, eventOrError) {
    const reason = type === 'close'
        ? `WebSocket closed (Code: ${eventOrError.code}, Clean: ${eventOrError.wasClean}, Reason: ${eventOrError.reason})`
        : `WebSocket error: ${eventOrError.message || 'Unknown error'}`;

    debug(reason);
    console.error(reason, eventOrError); // Log the event/error object too

    wsConnected = false;
    setStatus(type === 'close' ? `Disconnected (Code: ${eventOrError.code})` : "WebSocket error");

    // Stop audio capture if it was active
    if (isAudioCaptureActive || isRecording) {
        cleanupAudioProcessing(`WebSocket ${type}`); // Ensure audio resources are released
    }

    // Reset state and UI
    isAudioCaptureActive = false;
    isRecording = false;
    updateButtonUI(false);
    recordBtn.disabled = false; // Re-enable button if it was disabled during an attempt
    resetStateAfterError(`WebSocket ${type}`); // Reset message bubbles etc.
}

// --- WebSocket Message Handling ---
async function handleWebSocketMessage(e) {
    try {
        const data = JSON.parse(e.data);
        debug(`Received WS message: Type: ${data.type}`); // Less verbose logging

        switch (data.type) {
            case "text_delta":              handleTextDelta(data); break;
            case "text_done":               handleTextDone(data); break;
            case "audio_chunk":             handleAudioChunk(data); break;
            case "input_audio_transcript_delta": handleTranscriptDelta(data); break;
            case "input_audio_transcript_done": handleTranscriptDone(data); break;
            case "input_audio_buffer_committed": handleInputBufferCommitted(data); break;
            // Remove: case "done":                    handleDone(data); break;
            case "error":                   handleServerError(data); break;
            default:
                // Log other potentially useful events if needed, but less verbosely
                // Add "done" to the list of ignored types
                if (!["session.created", "input_audio_buffer.speech_started", "input_audio_buffer.speech_stopped", "conversation.item.created", "rate_limits.updated", "response.created", "response.output_item.added", "response.output_item.done", "response.content_part.added", "response.content_part.done", "response.audio.done", "response.done"].includes(data.type)) {
                    debug(`Unhandled/Info message type: ${data.type}`);
                }
        }
    } catch (err) {
        console.error(`Error handling WebSocket message: ${err.message}`, e.data);
        setStatus("Error processing message");
        debug(`Error handling message: ${err.message}`);
        resetStateAfterError(`Message processing error: ${err.message}`);
    }
}

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
            if (aiResponseBuffer !== null) { // Check if buffer object exists
                 debug(`Prepending buffered AI content: ${aiResponseBuffer.content}`);
                 initialContent += aiResponseBuffer.content;
                 // We don't reset the buffer here, handleTranscriptDone or handleInputBufferCommitted will
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

function handleTextDone(data) {
    debug(`AI text stream finished (text_done). userTranscriptFinalized=${userTranscriptFinalized}`);

    if (userTranscriptFinalized) {
        // Transcript already done, AI text finished, so turn is complete.
        debug("Resetting lastAiElem because transcript is finalized and text_done received.");
        lastAiElem = null; // Reset AI bubble reference for the next turn
        setStatus("Ready");
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

function handleAudioChunk(data) {
    playAudioChunk(data.audio);
}

function handleTranscriptDelta(data) {
    debug(`>>> handleTranscriptDelta received: ${data.content}`);
    // Simplified logic
    if (currentUserSpeechBubble === null) {
        debug("Creating user speech bubble for first transcript delta.");
        // Initialize with the first delta content directly
        currentUserSpeechBubble = createMessageBubble("user", "You: " + (data.content || ""));
        setStatus("Listening..."); // Update status
    } else {
        // Append subsequent deltas
        debug(`Appending transcript delta "${data.content || ''}" to user bubble.`);
        if (data.content) { // Ensure content exists before appending
            currentUserSpeechBubble.textContent += data.content;
        }
    }
    scrollToBottom();
}

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
    setStatus("Processing AI response..."); // Update status

    // Check if the AI text stream had already finished (buffer marked as done)
    if (wasBufferProcessed && aiResponseBuffer.done) {
        debug("Buffered content was processed and marked as done. Resetting lastAiElem.");
        lastAiElem = null; // Reset AI bubble, turn is complete
        setStatus("Ready"); // Set status to ready as the turn is fully complete
    }
    // If buffer existed but wasn't done, keep lastAiElem for subsequent text_deltas
    // If buffer didn't exist, subsequent text_deltas will create/use lastAiElem

    // Clear the buffer now that transcript is done and buffer (if any) was handled
    if (aiResponseBuffer !== null) {
        debug("Clearing aiResponseBuffer in handleTranscriptDone.");
        aiResponseBuffer = null;
    }
}

function handleInputBufferCommitted(data) {
    debug("Received input_audio_buffer_committed. Resetting flags for new turn.");
    userTranscriptFinalized = false;
    
    // Clear any potentially lingering buffer from an incomplete previous turn
    if (aiResponseBuffer !== null) {
        debug("Clearing aiResponseBuffer in handleInputBufferCommitted.");
        aiResponseBuffer = null;
    }

    debug(`userTranscriptFinalized set to FALSE.`);
    setStatus("Processing speech...");
    // This signals the start of potentially receiving user transcript deltas
    // and that subsequent AI text deltas should be buffered.
}

function handleServerError(data) {
    const errorMsg = data.message || "Unknown server error";
    setStatus(`Error: ${errorMsg}`);
    console.error(`WebSocket error message from server: ${errorMsg}`);
    debug(`Received error message: ${errorMsg}`);
    resetStateAfterError(`Server error: ${errorMsg}`); // Reset bubbles
    // Consider if audio capture needs stopping based on error type
}

// --- Text Message Sending ---
function sendTextMessage() {
  // Check wsConnected, not isAudioCaptureActive for text messages
  const text = inputEl.value.trim();
  if (!text || !wsConnected || ws?.readyState !== WebSocket.OPEN) {
      debug(`Cannot send text: wsConnected=${wsConnected}, ws.readyState=${ws?.readyState}`);
      setStatus("Not connected");
      return;
  }

  debug(`Sending text message: ${text}`);
  waitingForResponse = true; // Expect AI response
  setStatus("Sending message...");

  createMessageBubble("user", "You: " + text);

  // Send JSON over WebSocket
  ws.send(JSON.stringify({ type: "user_message", text }));
  inputEl.value = "";
  inputEl.focus();
  scrollToBottom();
}

// --- Audio Capture Control ---
async function toggleAudioCapture() {
  debug(`toggleAudioCapture called. isAudioCaptureActive: ${isAudioCaptureActive}`);
  if (isAudioCaptureActive) {
    stopCapture(); // New function name
  } else {
    await startCapture(); // New function name
  }
}

async function startCapture() {
    debug("Attempting to start audio capture...");

    // Add a temporary disabled state for the button while setup happens
    recordBtn.disabled = true;
    setStatus("Starting microphone...");

    // Resume AudioContext if needed
    try {
        const ctx = getAudioContext();
        if (ctx.state === 'suspended') {
            debug("AudioContext is suspended, attempting to resume before capture...");
            await ctx.resume();
            debug(`AudioContext resumed. State: ${ctx.state}`);
            if (ctx.state !== 'running') {
                 throw new Error(`AudioContext failed to resume (${ctx.state})`);
            }
        }
    } catch (err) {
        console.error("Error resuming AudioContext before capture:", err);
        handleAudioCaptureError(`Audio Resume Error: ${err.message}`);
        return; // Stop if resume fails
    }

    // Reset state for the new capture session *before* connecting or setting up audio
    debug("Resetting state for new audio capture session.");
    currentUserSpeechBubble = null;
    lastAiElem = null;
    userTranscriptFinalized = true; // Reset to TRUE
    aiResponseBuffer = null; // Reset buffer object to null
    debug(`userTranscriptFinalized reset to TRUE, aiResponseBuffer reset to null.`);

    // Ensure WebSocket is ready
    if (!wsConnected || ws?.readyState !== WebSocket.OPEN) {
        setStatus("Connecting...");
        debug("WebSocket not ready, attempting to initialize...");
        initWebSocket(async () => { // Pass setupAudioProcessing as callback
            debug("WebSocket connected after init, proceeding with audio setup.");
            // Set state *before* async setup call
            isAudioCaptureActive = true;
            updateButtonUI(true);
            setStatus("Connected, starting mic...");
            await setupAudioProcessing(); // Setup audio now that WS is ready
        });
        return; // Wait for the callback
    }

    // If WS was already connected
    isAudioCaptureActive = true;
    updateButtonUI(true);
    setStatus("Starting mic...");
    await setupAudioProcessing();
}

function stopCapture() {
    if (!isAudioCaptureActive) {
        debug("stopCapture called but not active.");
        return;
    }
    debug("Stopping audio capture (user request).");
    isAudioCaptureActive = false; // Mark user intent as stopped
    updateButtonUI(false);
    
    // Send speech_end signal to server before cleaning up
    try {
        if (wsConnected && ws?.readyState === WebSocket.OPEN) {
            debug("Sending speech_end signal to server");
            ws.send(JSON.stringify({
                type: "speech_end"
            }));
            setStatus("Processing...");
        } else {
            debug("Cannot send speech_end: WebSocket not connected");
            setStatus("Connection lost, try again");
        }
    } catch (err) {
        debug(`Error sending speech_end: ${err.message}`);
        console.error("Error sending speech_end:", err);
    }
    
    // Clean up audio processing resources
    cleanupAudioProcessing("User stopped capture");
}

// --- Audio Processing Setup & Cleanup ---
async function setupAudioProcessing() {
    debug(">>> setupAudioProcessing called");
    if (isRecording || sourceNode) {
        debug("setupAudioProcessing called but processing seems already active.");
        return; // Avoid duplicate setup
    }
    if (!isAudioCaptureActive || !wsConnected || ws?.readyState !== WebSocket.OPEN) {
      debug(`setupAudioProcessing blocked: isAudioCaptureActive=${isAudioCaptureActive}, wsConnected=${wsConnected}, wsState=${ws?.readyState}`);
      handleAudioCaptureError("Connection lost before mic start"); // Use error handler
      return;
    }

    setStatus("Initializing microphone...");
    try {
        const ctx = getAudioContext();
        if (ctx.state !== 'running') {
            debug("Attempting to resume AudioContext...");
            await ctx.resume();
            debug(`AudioContext resumed. New state: ${ctx.state}`);
            if (ctx.state !== 'running') throw new Error(`AudioContext failed to resume (${ctx.state})`);
        }

        debug("Requesting microphone access (getUserMedia)...");
        audioStream = await navigator.mediaDevices.getUserMedia({ audio: { /* consider adding specific constraints if needed */ } });
        debug("Microphone access granted.");

        sourceNode = ctx.createMediaStreamSource(audioStream);
        debug("Created sourceNode.");

        // Attempt AudioWorklet first
        let processorNode = await setupAudioWorklet(ctx, sourceNode);

        // Fallback to ScriptProcessor if Worklet failed
        if (!processorNode) {
            debug("Setting up ScriptProcessor as fallback...");
            processorNode = setupScriptProcessor(ctx, sourceNode);
        }

        if (!processorNode) throw new Error("Audio processor setup failed (both methods).");

        // Connect the source to the chosen processor
        sourceNode.connect(processorNode);
        // Do NOT connect processor to destination (unless ScriptProcessor needs it)
        if (processorNode.nodeType !== 'ScriptProcessorNode') {
             // Worklet doesn't need connecting to destination
        } else {
            // ScriptProcessor might need connecting to destination to stay alive in some browsers
            // processorNode.connect(ctx.destination); // Uncomment if needed, but usually not for sending data
        }
        debug("Source connected to processor.");

        isRecording = true; // Mark that processing is now active
        debug("Audio processor setup successful. isRecording = true");
        setStatus("Listening..."); // Update status *after* successful setup

    } catch (err) {
        console.error('Error setting up audio processing:', err);
        handleAudioCaptureError(`Mic/Setup Error: ${err.message}`); // Use centralized error handler
    }
}

async function setupAudioWorklet(ctx, source) {
    if (!ctx.audioWorklet) {
        debug("AudioWorklet not supported by this browser.");
        return null;
    }
    try {
        debug("Attempting AudioWorklet setup...");
        const workletCode = `
            class PCMProcessor extends AudioWorkletProcessor {
                constructor() {
                    super();
                    this.bufferSize = 2048; // Process in chunks
                    this.sampleRate = 24000; // Match OpenAI's rate
                }

                process(inputs, outputs) {
                    // Get mono input data
                    const input = inputs[0]?.[0]; // Optional chaining for safety
                    // Check isRecording flag inside the processor is tricky.
                    // Rely on disconnecting the node to stop processing.
                    if (input && input.length > 0) {
                        // Send data directly, rely on node disconnection to stop
                        this.port.postMessage({
                          pcmData: input
                        });
                    }
                    return true; // Keep processor alive until node disconnected
                }
            }

            registerProcessor('pcm-processor', PCMProcessor);
        `;
        const blob = new Blob([workletCode], { type: 'application/javascript' });
        const workletUrl = URL.createObjectURL(blob);
        // Consider revoking the URL later in cleanup if needed, though usually handled by browser

        await ctx.audioWorklet.addModule(workletUrl);
        debug("AudioWorklet module added.");
        const workletNode = new AudioWorkletNode(ctx, 'pcm-processor');
        debug("AudioWorkletNode created.");

        workletNode.port.onmessage = (event) => {
          // Send data ONLY if capture is intended AND WS is connected
          // isRecording flag check here might be redundant if node is disconnected promptly
          if (event.data.pcmData && isAudioCaptureActive && wsConnected && ws?.readyState === WebSocket.OPEN) {
            sendPCMDataToServer(event.data.pcmData);
          } else if (!isAudioCaptureActive) {
              // debug("Worklet message received but capture not active, stopping data send."); // Can be noisy
          }
        };
        // Don't connect source here, do it in the main setup function
        debug("Using AudioWorklet.");
        audioWorkletNode = workletNode; // Assign to global variable
        return workletNode;
    } catch (err) {
        console.error("AudioWorklet setup failed:", err);
        debug(`AudioWorklet setup failed: ${err.message}`);
        if (audioWorkletNode) { try { audioWorkletNode.disconnect(); } catch(e){} audioWorkletNode = null; }
        return null; // Indicate failure
    }
}

function setupScriptProcessor(ctx, source) {
    debug("Setting up ScriptProcessor...");
    const bufferSize = 4096; // Or another power of 2
    if (!ctx.createScriptProcessor) {
        console.error("ScriptProcessorNode is not supported.");
        setStatus("Error: Browser audio API outdated");
        debug("ScriptProcessorNode is not supported.");
        return false; // Indicate failure
    }
    try {
        scriptProcessorNode = ctx.createScriptProcessor(bufferSize, 1, 1);
        debug("ScriptProcessorNode created.");
        scriptProcessorNode.onaudioprocess = (e) => {
          // debug(\">>> ScriptProcessor onaudioprocess triggered\"); // Too noisy
          // Check isAudioCaptureActive and wsConnected
          if (isAudioCaptureActive && wsConnected && ws?.readyState === WebSocket.OPEN) {
            const inputData = e.inputBuffer.getChannelData(0);
            // Create a copy before sending if data needs to persist beyond this event
            sendPCMDataToServer(new Float32Array(inputData));
          } else {
              // debug(`ScriptProcessor skipping send: isAudioCaptureActive=${isAudioCaptureActive}, wsConnected=${wsConnected}`); // Too noisy
          }
        };
        // Don't connect source here, do it in the main setup function
        debug("Using ScriptProcessor.");
        return scriptProcessorNode;
    } catch (err) {
        console.error("Error setting up ScriptProcessor:", err);
        debug(`Error setting up ScriptProcessor: ${err.message}`);
        setStatus("Error: Audio processor setup failed");
        if (scriptProcessorNode) { try { scriptProcessorNode.disconnect(); } catch(e) {} }
        scriptProcessorNode = null;
        return false; // Indicate failure
    }
}

function cleanupAudioProcessing(reason) {
    debug(`Cleaning up audio processing resources. Reason: ${reason}`);
    // Check if cleanup is actually needed
    if (!isRecording && !sourceNode && !audioStream && !audioWorkletNode && !scriptProcessorNode) {
        debug("Cleanup called but no active resources found.");
        return;
    }

    const wasRecording = isRecording; // Store state before changing
    isRecording = false; // Mark processing as stopped *first*
    debug(`isRecording set to false (was ${wasRecording}).`);

    // Stop microphone track first
    if (audioStream) {
        debug("Stopping audio stream tracks.");
        audioStream.getTracks().forEach(track => {
            try { track.stop(); } catch(e) { console.warn("Error stopping track:", e); }
        });
        audioStream = null;
    }

    // Disconnect and nullify nodes - Use the specific global vars
    if (audioWorkletNode) {
        debug("Disconnecting AudioWorkletNode.");
        try {
            audioWorkletNode.port.close();
            audioWorkletNode.disconnect();
        } catch(e) { console.warn("Error disconnecting audioWorkletNode:", e); }
        audioWorkletNode = null;
    }
    if (scriptProcessorNode) {
        debug("Disconnecting ScriptProcessorNode.");
        try {
            scriptProcessorNode.disconnect();
            scriptProcessorNode.onaudioprocess = null;
        } catch(e) { console.warn("Error disconnecting scriptProcessorNode:", e); }
        scriptProcessorNode = null;
    }
    if (sourceNode) {
        debug("Disconnecting sourceNode.");
        try { sourceNode.disconnect(); } catch(e) { console.warn("Error disconnecting sourceNode:", e); }
        sourceNode = null;
    }
    debug("Finished cleaning up audio processing resources.");
}

function handleAudioCaptureError(errorMessage) {
    debug(`handleAudioCaptureError called. Error: ${errorMessage}`);
    console.error("Audio Capture Error:", errorMessage);
    setStatus(`Error: ${errorMessage.substring(0, 30)}${errorMessage.length > 30 ? '...' : ''}`);
    cleanupAudioProcessing(`Error: ${errorMessage}`); // Clean up resources
    // Ensure UI reflects the stopped state
    isAudioCaptureActive = false;
    isRecording = false;
    updateButtonUI(false); // Reset button to Talk state
    recordBtn.disabled = false; // Make sure button is enabled for retry
}

// --- PCM Data Sending ---
function sendPCMDataToServer(float32Data) {
  if (!float32Data || float32Data.length === 0) {
      // debug("sendPCMDataToServer called with empty data."); // Can be noisy
      return;
  }
  try {
    const int16Data = new Int16Array(float32Data.length);
    for (let i = 0; i < float32Data.length; i++) {
      const s = Math.max(-1, Math.min(1, float32Data[i]));
      int16Data[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    // debug(`Attempting to send ${int16Data.byteLength} bytes. isAudioCaptureActive: ${isAudioCaptureActive}, wsConnected: ${wsConnected}`); // Too noisy
    // Check capture active state AND WebSocket state
    if (isAudioCaptureActive && wsConnected && ws?.readyState === WebSocket.OPEN) {
        debug(">>> Sending PCM data via WebSocket"); // Log sending attempt
        ws.send(int16Data.buffer);
    } else {
        debug(`Skipping PCM send: isAudioCaptureActive=${isAudioCaptureActive}, wsConnected=${wsConnected}, ws.readyState=${ws?.readyState}`); // Log skipped send
    }
  } catch (err) {
    debug(`Error sending PCM data: ${err.message}`);
    console.error("Error in sendPCMDataToServer:", err);
  }
}

// --- Utility Functions ---
function updateButtonUI(isActive) {
    if (isActive) {
        recordBtn.classList.remove('bg-indigo-500');
        recordBtn.classList.add('bg-red-500');
        recordBtn.innerHTML = '<span class="mr-2">⏹️</span> Stop'; // Stop icon
    } else {
        recordBtn.classList.add('bg-indigo-500');
        recordBtn.classList.remove('bg-red-500');
        recordBtn.innerHTML = '<span class="mr-2">🎤</span> Talk'; // Talk icon
    }
    recordBtn.disabled = false; // Ensure enabled
}

function setStatus(message) {
    statusEl.textContent = message;
    debug(`Status updated: ${message}`);
}

function resetStateAfterError(reason) {
    debug(`Resetting state after error: ${reason}`);
    // Reset message bubbles
    currentUserSpeechBubble = null;
    lastAiElem = null;
    // Reset other relevant state
    userTranscriptFinalized = true; // Reset to TRUE
    aiResponseBuffer = null; // Reset buffer object to null
    debug(`userTranscriptFinalized reset to TRUE, aiResponseBuffer reset to null.`);
    // Don't reset isAudioCaptureActive or isRecording here, cleanup handles that
}

// --- Event Listeners & Initialization ---
sendBtn.addEventListener("click", sendTextMessage);
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    sendTextMessage(); // Renamed function
  }
});
recordBtn.addEventListener("click", toggleAudioCapture);

// DOMContentLoaded: Connect WebSocket immediately
document.addEventListener("DOMContentLoaded", () => {
    debug("DOM Content Loaded. Initializing WebSocket...");
    initWebSocket(); // Connect WebSocket on page load
    setStatus("Connecting...");
    try {
        getAudioContext(); // Initialize context early
        debug("AudioContext obtained/initialized.");
    } catch (e) {
        console.error(`Fatal: Error initializing audio context: ${e}`);
        setStatus("Error: Audio Not Supported");
        debug("AudioContext initialization failed.");
        recordBtn.disabled = true;
        recordBtn.title = "Audio context failed to initialize.";
    }
});

// Keep audio context running (existing)
document.body.addEventListener("click", () => {
  const ctx = getAudioContext();
  if (ctx && ctx.state === 'suspended') {
    debug("Body click detected, resuming suspended AudioContext...");
    ctx.resume().then(() => {
        debug(`AudioContext resumed. State: ${ctx.state}`);
    }).catch(e => {
        console.error("Error resuming AudioContext on click:", e);
        debug(`Error resuming AudioContext: ${e.message}`);
    });
  }
});

// --- Debug Function ---
const DEBUG = true; // Keep debug flag
function debug(msg) {
  if (!DEBUG) return;
  console.log(msg);
  debugEl.classList.remove("hidden");
  debugEl.textContent += msg + "\n";
  if (debugEl.textContent.length > 1000) {
    debugEl.textContent = debugEl.textContent.slice(-1000);
  }
}

// --- Message Bubble Creation ---
function createMessageBubble(sender, initialText) {
    const bubbleDiv = document.createElement("div");
    bubbleDiv.textContent = initialText;
    if (sender === "user") {
        bubbleDiv.className = "self-end bg-blue-100 rounded p-2 max-w-xs";
    } else { // AI
        bubbleDiv.className = "self-start bg-gray-100 rounded p-2 max-w-xs";
    }
    messagesDiv.appendChild(bubbleDiv);
    scrollToBottom(); // Scroll when adding
    return bubbleDiv;
}

// --- Scroll Helper ---
function scrollToBottom() {
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}