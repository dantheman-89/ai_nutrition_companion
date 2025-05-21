// Audio Module - Handles audio capture, processing and playback
import * as WSClient from './wsclient.js';
import * as UI from './ui.js';


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

// Track if the worklet module has been loaded
let workletModuleLoaded = false;

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


// ------------------------------------------------
// Audio Recording Functions
// ------------------------------------------------
/**
 * Set up audio capture and processing
 * @param {boolean} isAudioCaptureActive - Whether audio capture is active
 * @param {boolean} wsConnected - Whether WebSocket is connected
 * @param {WebSocket} ws - WebSocket instance
 */
async function setupAudioProcessing(isAudioCaptureActive, wsConnected, ws) {
  UI.debug(">>> setupAudioProcessing called");
  
  // Check if already recording
  if (isRecording || sourceNode) {
    UI.debug("setupAudioProcessing called but processing seems already active.");
    return; // Avoid duplicate setup
  }
  
  // Check requirements for audio setup
  if (!isAudioCaptureActive || !wsConnected || ws?.readyState !== window.WebSocket.OPEN) {
    UI.debug(`setupAudioProcessing blocked: isAudioCaptureActive=${isAudioCaptureActive}, wsConnected=${wsConnected}, wsState=${ws?.readyState}`);
    return false;
  }

  try {
    // Initialize and resume audio context
    const ctx = getAudioContext();
    if (ctx.state !== 'running') {
      UI.debug("Attempting to resume AudioContext...");
      await ctx.resume();
      UI.debug(`AudioContext resumed. New state: ${ctx.state}`);
      if (ctx.state !== 'running') throw new Error(`AudioContext failed to resume (${ctx.state})`);
    }

    // Get microphone access
    UI.debug("Requesting microphone access (getUserMedia)...");
    audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    UI.debug("Microphone access granted.");

    // Create source from microphone
    sourceNode = ctx.createMediaStreamSource(audioStream);
    UI.debug("Created sourceNode.");

    // Attempt AudioWorklet first
    let processorNode = await setupAudioWorklet(ctx, sourceNode, ws);

    // Fallback to ScriptProcessor if Worklet failed
    if (!processorNode) {
      processorNode = setupScriptProcessor(ctx, sourceNode, ws);
      if (!processorNode) {
        throw new Error("Failed to setup audio processing");
      }
    }

    // Connect source to processor
    sourceNode.connect(processorNode);
    UI.debug("Audio nodes connected.");
    
    // Set recording state
    isRecording = true;
    return true;

  } catch (err) {
    UI.debug(`Audio setup error: ${err.message}`);
    console.error("Audio setup error:", err);
    cleanupAudioResources();
    return false;
  }
}

// Set up AudioWorklet for audio processing
async function setupAudioWorklet(ctx, source, ws) {
  if (!ctx.audioWorklet) {
    UI.debug("AudioWorklet not supported by this browser.");
    return null;
  }
  
  try {
    UI.debug("Attempting AudioWorklet setup...");
    
    // Only load the module once
    if (!workletModuleLoaded) {
      await ctx.audioWorklet.addModule('/static/js/pcmprocessor.js');
      workletModuleLoaded = true;
      UI.debug("AudioWorklet module added.");
    } else {
      UI.debug("AudioWorklet module already loaded, reusing.");
    }

    // Create new processor node
    const workletNode = new AudioWorkletNode(ctx, 'pcm-processor', {
      numberOfInputs: 1,
      numberOfOutputs: 0,
      channelCount: 1
    });
    UI.debug("AudioWorkletNode created.");

    // Set up message handling from processor
    workletNode.port.onmessage = (event) => {
      if (event.data.pcmData) {
        processAudioChunk(event.data.pcmData);
      }
    };
    
    audioWorkletNode = workletNode;
    UI.debug("Using AudioWorklet for audio processing.");
    return workletNode;
  } catch (err) {
    console.error("AudioWorklet setup failed:", err);
    UI.debug(`AudioWorklet setup failed: ${err.message}`);
    return null;
  }
}

// Process audio chunks and send to server
function processAudioChunk(audioData) {
  // Add to buffer
  audioChunkBuffer.push(new Float32Array(audioData));
  
  // Set up timer to send batches if not already running
  if (!audioChunkTimer) {
    audioChunkTimer = setInterval(() => {
      if (audioChunkBuffer.length > 0) {
        // Convert and send
        const combinedData = combineAudioChunks(audioChunkBuffer);
        sendAudioChunk(combinedData);
        // Clear buffer
        audioChunkBuffer = [];
      }
    }, BATCH_INTERVAL_MS);
  }
}

// Combine audio chunks into a single Float32Array
function combineAudioChunks(chunks) {
  // Calculate total length
  let totalLength = 0;
  for (const chunk of chunks) {
    totalLength += chunk.length;
  }
  
  // Create combined array
  const result = new Float32Array(totalLength);
  let offset = 0;
  
  // Copy each chunk
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.length;
  }
  
  return result;
}

function sendAudioChunk(audioData) {
  if (!WSClient.isConnected()) {
    UI.debug("Cannot send audio: WebSocket not connected");
    return;
  }

  try {
    const pcm16 = convertFloat32ToInt16(audioData); // Convert Float32Array to Int16Array
    const audio_base64 = btoa(String.fromCharCode.apply(null, new Uint8Array(pcm16.buffer)));  // Convert ArrayBuffer to Base64 string
    
    // Send JSON message with base64 audio
    const message = {
      type: "user_audio_chunk",
      payload: {
        audio: audio_base64
      }
    };
    WSClient.ws.send(JSON.stringify(message));
  } catch (err) {
    UI.debug(`Error sending audio: ${err.message}`);
    console.error("Error sending audio:", err);
  }
}

// Helper function to convert audio format
function convertFloat32ToInt16(float32Array) {
  const int16Array = new Int16Array(float32Array.length);
  
  for (let i = 0; i < float32Array.length; i++) {
    // Convert float32 [-1.0, 1.0] to int16 [-32768, 32767]
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }
  
  return int16Array;
}

// Cleanup audio resources
function cleanupAudioResources() {
  UI.debug("Cleaning up audio resources");
  
  // Clear batch timer
  if (audioChunkTimer) {
    clearInterval(audioChunkTimer);
    audioChunkTimer = null;
  }
  
  // Disconnect audio nodes
  if (sourceNode) {
    sourceNode.disconnect();
    sourceNode = null;
  }
  
  if (audioWorkletNode) {
    audioWorkletNode.disconnect();
    audioWorkletNode = null;
  }
  
  if (scriptProcessorNode) {
    scriptProcessorNode.disconnect();
    scriptProcessorNode = null;
  }
  
  // Stop media stream tracks
  if (audioStream) {
    audioStream.getTracks().forEach(track => track.stop());
    audioStream = null;
  }
  
  isRecording = false;
  audioChunkBuffer = [];
}

// Start audio capture
function startAudioCapture(wsConnected, ws) {
  if (isRecording) return;
  
  isAudioCaptureActive = true;
  UI.updateButtonUI(true);
  
  // Send speech_start signal
  sendSpeechStartSignal();
  
  // Set up audio processing
  setupAudioProcessing(isAudioCaptureActive, wsConnected, ws);
}

// Stop audio capture
function stopAudioCapture() {
  if (!isAudioCaptureActive) return;
  
  isAudioCaptureActive = false;
  UI.updateButtonUI(false);
  
  // Send speech_end signal
  sendSpeechEndSignal();
  
  cleanupAudioResources();
}


// Add this function to wsclient.js
function sendSpeechStartSignal() {
  try {
    if (!WSClient.isConnected()) {
      UI.debug("Cannot send speech_start: WebSocket not connected");
      return false;
    }
    
    UI.debug("Sending speech_start signal to server");
    const message = {
      type: "speech_start",
      payload: {}
    };
    WSClient.ws.send(JSON.stringify(message));

    return true;
  } catch (err) {
    UI.debug(`Error sending speech_start: ${err.message}`);
    console.error("Error sending speech_start:", err);
    return false;
  }
}

function sendSpeechEndSignal() {
  try {
    if (!WSClient.isConnected()) {
      UI.debug("Cannot send speech_end: WebSocket not connected");
      return false;
    }
    
    UI.debug("Sending speech_end signal to server");
    const message = {
      type: "speech_end",
      payload: {}
    };
    WSClient.ws.send(JSON.stringify(message));

    return true;
  } catch (err) {
    UI.debug(`Error sending speech_end: ${err.message}`);
    console.error("Error sending speech_end:", err);
    return false;
  }
}

// Fallback: Setup ScriptProcessor for older browsers
function setupScriptProcessor(ctx, source) {
  try {
    UI.debug("Falling back to ScriptProcessor");
    
    // Create script processor node (buffer size must be power of 2)
    const bufferSize = 8192; // 8kHz
    const scriptNode = ctx.createScriptProcessor(bufferSize, 1, 1);
    
    scriptNode.onaudioprocess = (audioProcessEvent) => {
      const inputBuffer = audioProcessEvent.inputBuffer;
      const inputData = inputBuffer.getChannelData(0);
      processAudioChunk(inputData);
    };
    
    scriptProcessorNode = scriptNode;
    return scriptNode;
  } catch (err) {
    console.error("ScriptProcessor setup failed:", err);
    UI.debug(`ScriptProcessor setup failed: ${err.message}`);
    return null;
  }
}
// --------------------------------------
// Export public API
// --------------------------------------

export {
  startAudioCapture,
  stopAudioCapture,
  playAudioChunk,
  isRecording
};