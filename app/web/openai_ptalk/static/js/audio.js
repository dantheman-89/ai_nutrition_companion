// Audio Module - Handles audio capture, processing and playback
import * as WebSocket from './websocket.js';
import { debug } from './ui.js';


// Audio playback state
let audioContext;
let audioQueue = [];
let isPlaying = false;

// Audio capture state
let audioStream = null;
let sourceNode = null;
let audioWorkletNode = null;
let scriptProcessorNode = null;
let isRecording = false;
let isAudioCaptureActive = false; 

// Audio processing state
let audioChunkBuffer = [];
let audioChunkTimer = null;
const BATCH_INTERVAL_MS = 200;

// ------------------------------------------------
// Audio Playback Functions
// ------------------------------------------------

// Get or create the audio context
function getAudioContext() {
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: 24000 // Match OpenAI's expected sample rate
    });
  }
  return audioContext;
}


// Convert base64 string to array buffer
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


// Queue and play audio data
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


// Play the next audio chunk from the queue
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

/**
 * Set up audio capture and processing
 * @param {boolean} isAudioCaptureActive - Whether audio capture is active
 * @param {boolean} wsConnected - Whether WebSocket is connected
 * @param {WebSocket} ws - WebSocket instance
 */
async function setupAudioProcessing(isAudioCaptureActive, wsConnected, ws) {
  debug(">>> setupAudioProcessing called");
  if (isRecording || sourceNode) {
    debug("setupAudioProcessing called but processing seems already active.");
    return; // Avoid duplicate setup
  }
  if (!isAudioCaptureActive || !wsConnected || ws?.readyState !== WebSocket.OPEN) {
    debug(`setupAudioProcessing blocked: isAudioCaptureActive=${isAudioCaptureActive}, wsConnected=${wsConnected}, wsState=${ws?.readyState}`);
    return false;
  }

  try {
    const ctx = getAudioContext();
    if (ctx.state !== 'running') {
      debug("Attempting to resume AudioContext...");
      await ctx.resume();
      debug(`AudioContext resumed. New state: ${ctx.state}`);
      if (ctx.state !== 'running') throw new Error(`AudioContext failed to resume (${ctx.state})`);
    }

    debug("Requesting microphone access (getUserMedia)...");
    audioStream = await navigator.mediaDevices.getUserMedia({ audio: {} });
    debug("Microphone access granted.");

    sourceNode = ctx.createMediaStreamSource(audioStream);
    debug("Created sourceNode.");

    // Attempt AudioWorklet first
    let processorNode = await setupAudioWorklet(ctx, sourceNode, isAudioCaptureActive, wsConnected, ws);

    // Fallback to ScriptProcessor if Worklet failed
    if (!processorNode) {
      debug("Setting up ScriptProcessor as fallback...");
      processorNode = setupScriptProcessor(ctx, sourceNode, isAudioCaptureActive, wsConnected, ws);
    }

    if (!processorNode) throw new Error("Audio processor setup failed (both methods).");

    // Connect the source to the chosen processor
    sourceNode.connect(processorNode);
    debug("Source connected to processor.");

    isRecording = true; // Mark that processing is now active
    debug("Audio processor setup successful. isRecording = true");
    return true;

  } catch (err) {
    console.error('Error setting up audio processing:', err);
    return false;
  }
}


// ------------------------------------------------
// Audio Recording Functions
// ------------------------------------------------

// Set up AudioWorklet for audio processing
async function setupAudioWorklet(ctx, source, isAudioCaptureActive, wsConnected, ws) {
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
          this.bufferSize = 8192; // Process in chunks
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

    await ctx.audioWorklet.addModule(workletUrl);
    debug("AudioWorklet module added.");
    const workletNode = new AudioWorkletNode(ctx, 'pcm-processor');
    debug("AudioWorkletNode created.");

    workletNode.port.onmessage = (event) => {
      // Send data ONLY if capture is intended AND WS is connected
      if (event.data.pcmData && isAudioCaptureActive && wsConnected && ws?.readyState === WebSocket.OPEN) {
        sendPCMDataToServer(event.data.pcmData, isAudioCaptureActive, wsConnected, ws);
      }
    };
    audioWorkletNode = workletNode; // Assign to global variable
    debug("Using AudioWorklet.");
    return workletNode;
  } catch (err) {
    console.error("AudioWorklet setup failed:", err);
    debug(`AudioWorklet setup failed: ${err.message}`);
    if (audioWorkletNode) { 
      try { audioWorkletNode.disconnect(); } catch(e){} 
      audioWorkletNode = null; 
    }
    return null; // Indicate failure
  }
}


// Set up ScriptProcessor fallback for audio processing
function setupScriptProcessor(ctx, source, isAudioCaptureActive, wsConnected, ws) {
  debug("Setting up ScriptProcessor...");
  const bufferSize = 16384; // Or another power of 2
  if (!ctx.createScriptProcessor) {
    console.error("ScriptProcessorNode is not supported.");
    debug("ScriptProcessorNode is not supported.");
    return false; // Indicate failure
  }
  try {
    scriptProcessorNode = ctx.createScriptProcessor(bufferSize, 1, 1);
    debug("ScriptProcessorNode created.");
    scriptProcessorNode.onaudioprocess = (e) => {
      // Check isAudioCaptureActive and wsConnected
      if (isAudioCaptureActive && wsConnected && ws?.readyState === WebSocket.OPEN) {
        const inputData = e.inputBuffer.getChannelData(0);
        // Create a copy before sending if data needs to persist beyond this event
        sendPCMDataToServer(new Float32Array(inputData), isAudioCaptureActive, wsConnected, ws);
      }
    };
    debug("Using ScriptProcessor.");
    return scriptProcessorNode;
  } catch (err) {
    console.error("Error setting up ScriptProcessor:", err);
    debug(`Error setting up ScriptProcessor: ${err.message}`);
    if (scriptProcessorNode) { 
      try { scriptProcessorNode.disconnect(); } catch(e) {} 
    }
    scriptProcessorNode = null;
    return false; // Indicate failure
  }
}


// Clean up audio processing resources
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

  // Disconnect and nullify nodes
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


// Send PCM data to the server
function sendPCMDataToServer(float32Data, isAudioCaptureActive, wsConnected, ws) {
  if (!float32Data || float32Data.length === 0) {
    return;
  }

  try {
    // Basic voice activity detection to reduce silent packets
    const sum = float32Data.reduce((acc, val) => acc + Math.abs(val), 0);
    const avg = sum / float32Data.length;
    const isVoice = avg > 0.005; // Adjust threshold as needed

    // Skip some silence packets (send ~25% of silence)
    if (!isVoice && Math.random() > 0.25) {
      return;
    }
    
    // Convert to Int16 format
    const int16Data = new Int16Array(float32Data.length);
    for (let i = 0; i < float32Data.length; i++) {
      const s = Math.max(-1, Math.min(1, float32Data[i]));
      int16Data[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }

    // Add to batch buffer
    audioChunkBuffer.push(int16Data.buffer);
    
    // Start timer if not running
    if (!audioChunkTimer) {
      audioChunkTimer = setTimeout(() => {
        if (audioChunkBuffer.length > 0 && isAudioCaptureActive && 
            wsConnected && ws?.readyState === WebSocket.OPEN) {
          
          // Combine buffers if multiple chunks available
          let dataToSend;
          if (audioChunkBuffer.length > 1) {
            dataToSend = concatAudioBuffers(audioChunkBuffer);
            debug(`Sending batched audio: ${audioChunkBuffer.length} chunks (${dataToSend.byteLength} bytes)`);
          } else {
            // Just send the single buffer directly
            dataToSend = audioChunkBuffer[0];
            debug(`Sending single audio chunk (${dataToSend.byteLength} bytes)`);
          }
          
          // Send the data
          ws.send(dataToSend);
        } else if (audioChunkBuffer.length > 0) {
          debug(`Dropped ${audioChunkBuffer.length} audio chunks - connection not ready`);
        }
        
        // Reset buffer and timer
        audioChunkBuffer = [];
        audioChunkTimer = null;
      }, BATCH_INTERVAL_MS);
    }
    
  } catch (err) {
    debug(`Error processing PCM data: ${err.message}`);
    console.error("Error in sendPCMDataToServer:", err);
    
    // Reset buffer and timer in case of error
    audioChunkBuffer = [];
    if (audioChunkTimer) {
      clearTimeout(audioChunkTimer);
      audioChunkTimer = null;
    }
  }
}


// Combine multiple audio buffers into one
function concatAudioBuffers(buffers) {
  // Calculate total length
  const totalLength = buffers.reduce((acc, buf) => acc + buf.byteLength, 0);
  const result = new ArrayBuffer(totalLength);
  const view = new Uint8Array(result);
  
  // Copy data
  let offset = 0;
  for (const buffer of buffers) {
    view.set(new Uint8Array(buffer), offset);
    offset += buffer.byteLength;
  }
  
  return result;
}


// -----------------------------------------
// Toggle audio capture
// -----------------------------------------
async function toggleAudioCapture() {
  UI.debug(`toggleAudioCapture called. isAudioCaptureActive: ${isAudioCaptureActive}`);
  if (isAudioCaptureActive) {
    stopCapture();
  } else {
    await startCapture();
  }
}

/**
 * Start audio capture
 */
async function startCapture() {
  UI.debug("Attempting to start audio capture...");

  // Add a temporary disabled state for the button while setup happens
  UI.elements.recordBtn.disabled = true;

  // Resume AudioContext if needed
  try {
    const ctx = Audio.getAudioContext();
    if (ctx.state === 'suspended') {
      UI.debug("AudioContext is suspended, attempting to resume before capture...");
      await ctx.resume();
      UI.debug(`AudioContext resumed. State: ${ctx.state}`);
      if (ctx.state !== 'running') {
        throw new Error(`AudioContext failed to resume (${ctx.state})`);
      }
    }
  } catch (err) {
    console.error("Error resuming AudioContext before capture:", err);
    handleAudioCaptureError(`Audio Resume Error: ${err.message}`);
    return; // Stop if resume fails
  }

  // Reset state for new audio capture session
  resetChatStateForNewCapture();

  // Ensure WebSocket is ready
  if (!WebSocket.isWebSocketConnected()) {
    UI.debug("WebSocket not ready, attempting to initialize...");
    WebSocket.initWebSocket(async () => {
      // Set state *before* async setup call
      isAudioCaptureActive = true;
      UI.updateButtonUI(true);
      await setupCapture();
    });
    return; // Wait for the callback
  }

  // If WS was already connected
  isAudioCaptureActive = true;
  UI.updateButtonUI(true);
  await setupCapture();
}

/**
 * Reset chat state for new capture session
 */
function resetChatStateForNewCapture() {
  // Reset UI state
  WebSocket.setCurrentUserSpeechBubble(null);
  WebSocket.setLastAiElem(null);
}

/**
 * Set up audio capture
 */
async function setupCapture() {
  const ws = WebSocket.getWebSocket();
  const wsConnected = WebSocket.isWebSocketConnected();
  
  const success = await Audio.setupAudioProcessing(isAudioCaptureActive, wsConnected, ws);
  if (!success) {
    handleAudioCaptureError("Failed to set up audio processing");
  }
}

/**
 * Stop audio capture
 */
function stopCapture() {
  if (!isAudioCaptureActive) {
    UI.debug("stopCapture called but not active.");
    return;
  }
  UI.debug("Stopping audio capture (user request).");
  isAudioCaptureActive = false;
  UI.updateButtonUI(false);
  
  // Send speech_end signal to server
  if (WebSocket.sendSpeechEndSignal()) {
    // Signal sent successfully
  }
  
  // Clean up audio processing resources
  Audio.cleanupAudioProcessing("User stopped capture");
}

/**
 * Handle audio capture errors
 */
function handleAudioCaptureError(errorMessage) {
  UI.debug(`handleAudioCaptureError called. Error: ${errorMessage}`);
  console.error("Audio Capture Error:", errorMessage);
  Audio.cleanupAudioProcessing(`Error: ${errorMessage}`);
  isAudioCaptureActive = false;
  UI.updateButtonUI(false);
  UI.elements.recordBtn.disabled = false;
}


// Check if the audio system is recording
function getIsRecording() {
  return isRecording;
}

// --------------------------------------
// Export public API
// --------------------------------------

export {
  getAudioContext,
  playAudioChunk,
  setupAudioProcessing,
  cleanupAudioProcessing,
  getIsRecording,
  toggleAudioCapture
};