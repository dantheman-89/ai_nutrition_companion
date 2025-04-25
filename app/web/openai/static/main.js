// Global variables for audio handling
let mediaRecorder;
let audioChunks = [];
let isRecording = false;
let ws;
let audioQueue = [];
let isPlaying = false;
let sessionActive = false;
let conversationHistory = [];
let reconnectAttempts = 0;
let maxReconnectAttempts = 5;
let reconnectDelay = 1000; // Start with 1 second

// Wait for DOM to load
document.addEventListener('DOMContentLoaded', () => {
    // DOM elements
    const toggleButton = document.getElementById('toggle-recording');
    const recordingIndicator = document.getElementById('recording-indicator');
    const statusElement = document.getElementById('status');
    const messagesContainer = document.getElementById('chat-messages');

    // Add error reporting
    function reportError(message, error = null) {
        console.error(message, error);
        const errorDiv = document.createElement('div');
        errorDiv.className = 'status-message error';
        errorDiv.textContent = message;
        messagesContainer.appendChild(errorDiv);
        scrollToBottom();
    }

    // Initialize WebSocket connection
    function initializeWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        console.log(`Connecting to WebSocket at ${wsUrl}`);
        
        if (ws) {
            // Close existing connection if any
            if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
                ws.close();
            }
        }
        
        ws = new WebSocket(wsUrl);
        ws.binaryType = "arraybuffer";
        
        ws.onopen = () => {
            console.log("WebSocket connection opened");
            statusElement.textContent = 'Connected';
            toggleButton.disabled = false;
            addStatusMessage("Connected to server");
            reconnectAttempts = 0; // Reset reconnect counter on successful connection
            reconnectDelay = 1000;  // Reset delay
        };
        
        ws.onclose = (event) => {
            console.log(`WebSocket connection closed: ${event.code} - ${event.reason}`);
            statusElement.textContent = 'Disconnected';
            toggleButton.disabled = isRecording ? true : false;
            sessionActive = false;
            
            // If we were recording, stop the UI elements
            if (isRecording) {
                isRecording = false;
                toggleButton.textContent = 'Start Recording';
                toggleButton.classList.remove('recording');
                recordingIndicator.classList.remove('active');
            }
            
            // Attempt to reconnect with exponential backoff, but only if the page is still active
            if (document.visibilityState === 'visible' && reconnectAttempts < maxReconnectAttempts) {
                const delay = Math.min(reconnectDelay * Math.pow(1.5, reconnectAttempts), 10000);
                reconnectAttempts++;
                
                addStatusMessage(`Connection closed. Attempting to reconnect in ${Math.round(delay/1000)} seconds... (${reconnectAttempts}/${maxReconnectAttempts})`);
                
                setTimeout(() => {
                    if (document.visibilityState === 'visible') {
                        addStatusMessage("Reconnecting...");
                        initializeWebSocket();
                    }
                }, delay);
            } else if (reconnectAttempts >= maxReconnectAttempts) {
                addStatusMessage("Maximum reconnection attempts reached. Please refresh the page.");
                toggleButton.textContent = 'Refresh to Reconnect';
                toggleButton.disabled = false;
                toggleButton.onclick = () => window.location.reload();
            } else {
                addStatusMessage("Disconnected from server.");
            }
        };

        ws.onerror = (error) => {
            console.error("WebSocket error:", error);
            reportError("Connection error. Check console for details.");
        };
        
        ws.onmessage = async ({ data }) => {
            if (typeof data === "string") {
                try {
                    const msg = JSON.parse(data);
                    console.log("Received message:", msg);
                    
                    switch (msg.type) {
                        case 'status':
                            addStatusMessage(msg.message);
                            break;
                        case 'error':
                            reportError(msg.message);
                            break;
                        case 'session.created':
                            sessionActive = true;
                            statusElement.textContent = `Session: ${msg.session_id}`;
                            addStatusMessage(`Session created: ${msg.session_id}`);
                            break;
                        case 'user_transcript':
                            addMessage(msg.text, 'user');
                            break;
                        case 'assistant_transcript':
                            updateOrCreateAssistantMessage(msg.text);
                            break;
                    }
                } catch (e) {
                    console.error('Error parsing message:', e);
                    reportError(`Failed to parse server message: ${e.message}`);
                }
            } else {
                // Handle audio data
                console.log(`Received audio data: ${data.byteLength} bytes`);
                audioQueue.push(new Blob([data], { type: 'audio/mpeg' }));
                if (!isPlaying) {
                    playNextInQueue();
                }
            }
        };
    }

    // Initialize audio recording
    async function initializeRecording() {
        try {
            console.log("Requesting microphone access...");
            const stream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    channelCount: 1,
                    sampleRate: 16000
                } 
            });
            console.log("Microphone access granted");
            
            // Create an audio context for the VU meter
            const audioContext = new AudioContext();
            const source = audioContext.createMediaStreamSource(stream);
            const analyzer = audioContext.createAnalyser();
            analyzer.fftSize = 256;
            source.connect(analyzer);
            
            // Find supported MIME types for this browser
            const mimeTypes = [
                'audio/webm;codecs=opus',
                'audio/webm',
                'audio/ogg;codecs=opus',
                'audio/ogg'
            ];
            
            let selectedMimeType = '';
            for (const type of mimeTypes) {
                if (MediaRecorder.isTypeSupported(type)) {
                    selectedMimeType = type;
                    console.log(`Using MIME type: ${selectedMimeType}`);
                    break;
                }
            }
            
            if (!selectedMimeType) {
                throw new Error('No supported MIME types found for MediaRecorder');
            }
            
            // Set up media recorder with appropriate settings
            const options = { 
                mimeType: selectedMimeType,
                audioBitsPerSecond: 16000
            };
            
            mediaRecorder = new MediaRecorder(stream, options);
            
            mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    // Send audio data immediately to server
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        console.log(`Sending audio chunk: ${event.data.size} bytes`);
                        ws.send(event.data);
                    } else {
                        console.warn("WebSocket not ready when audio data available");
                        audioChunks.push(event.data);  // Store for later sending if needed
                    }
                }
            };
            
            // Create VU meter element if it doesn't exist
            if (!document.getElementById('vu-meter')) {
                const controls = document.querySelector('.chat-controls');
                const vuMeter = document.createElement('div');
                vuMeter.id = 'vu-meter';
                vuMeter.className = 'vu-meter';
                
                const vuMeterLevel = document.createElement('div');
                vuMeterLevel.id = 'vu-meter-level';
                vuMeterLevel.className = 'vu-meter-level';
                
                vuMeter.appendChild(vuMeterLevel);
                controls.appendChild(vuMeter);
            }
            
            // Function to update VU meter
            function updateVUMeter() {
                if (!analyzer || !isRecording) return;
                
                const dataArray = new Uint8Array(analyzer.frequencyBinCount);
                analyzer.getByteFrequencyData(dataArray);
                
                // Calculate average volume
                const average = dataArray.reduce((sum, value) => sum + value, 0) / dataArray.length;
                const level = Math.min(100, Math.max(0, average * 1.5)); // Scale up a bit for better visibility
                
                const vuMeterLevel = document.getElementById('vu-meter-level');
                if (vuMeterLevel) {
                    vuMeterLevel.style.width = `${level}%`;
                }
                
                if (isRecording) {
                    requestAnimationFrame(updateVUMeter);
                } else if (vuMeterLevel) {
                    vuMeterLevel.style.width = '0%';
                }
            }
            
            return { stream, updateVUMeter, selectedMimeType };
        } catch (error) {
            console.error('Error accessing microphone:', error);
            reportError(`Microphone access error: ${error.message}`);
            return null;
        }
    }

    // Toggle recording
    let vuMeterUpdater;
    async function toggleRecording() {
        try {
            if (!isRecording) {
                // First time or reconnect - initialize WebSocket first
                if (!ws || ws.readyState !== WebSocket.OPEN) {
                    addStatusMessage("Connecting to server...");
                    initializeWebSocket();
                    
                    // Wait a bit for the WebSocket to connect
                    await new Promise(resolve => setTimeout(resolve, 500));
                    
                    if (!ws || ws.readyState !== WebSocket.OPEN) {
                        reportError("Could not connect to server. Please try again.");
                        return;
                    }
                }
                
                // Initialize recording if needed
                if (!mediaRecorder) {
                    addStatusMessage("Requesting microphone access...");
                    const result = await initializeRecording();
                    if (!result) {
                        reportError("Could not access microphone. Please check your permissions and try again.");
                        return;
                    }
                    
                    mediaRecorder = new MediaRecorder(result.stream, {
                        mimeType: result.selectedMimeType,
                        audioBitsPerSecond: 16000
                    });
                    
                    mediaRecorder.ondataavailable = (event) => {
                        if (ws && ws.readyState === WebSocket.OPEN && event.data.size > 0) {
                            ws.send(event.data);
                        } else if (event.data.size > 0) {
                            audioChunks.push(event.data);
                        }
                    };
                    
                    vuMeterUpdater = result.updateVUMeter;
                }
                
                // Clear any previously stored chunks
                audioChunks = [];
                
                // Start recording
                addStatusMessage("Starting recording...");
                mediaRecorder.start(100); // Send audio chunks every 100ms
                isRecording = true;
                toggleButton.textContent = 'Stop Recording';
                toggleButton.classList.add('recording');
                recordingIndicator.classList.add('active');
                
                // Start VU meter animation
                if (vuMeterUpdater) {
                    requestAnimationFrame(vuMeterUpdater);
                }
                
                // If reconnecting, send a reconnect command
                if (!sessionActive && ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({ command: "reconnect" }));
                }
            } else {
                // Stop recording
                addStatusMessage("Stopping recording...");
                if (mediaRecorder && mediaRecorder.state !== 'inactive') {
                    mediaRecorder.stop();
                    
                    // Send a stop command to the server
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({ command: "stop" }));
                    }
                }
                
                isRecording = false;
                toggleButton.textContent = 'Start Recording';
                toggleButton.classList.remove('recording');
                recordingIndicator.classList.remove('active');
                
                const vuMeterLevel = document.getElementById('vu-meter-level');
                if (vuMeterLevel) {
                    vuMeterLevel.style.width = '0%';
                }
                
                // If we have stored audio chunks and the WebSocket is now open, send them
                if (audioChunks.length > 0 && ws && ws.readyState === WebSocket.OPEN) {
                    for (const chunk of audioChunks) {
                        ws.send(chunk);
                    }
                    audioChunks = [];
                }
            }
        } catch (error) {
            reportError(`Error toggling recording: ${error.message}`, error);
            // Reset UI state on error
            isRecording = false;
            toggleButton.textContent = 'Start Recording';
            toggleButton.classList.remove('recording');
            recordingIndicator.classList.remove('active');
        }
    }

    // Add a message to the chat
    function addMessage(text, sender) {
        if (!text || !text.trim()) return; // Don't add empty messages
        
        const messageDiv = document.createElement('div');
        messageDiv.classList.add('message', sender);
        messageDiv.textContent = text;
        messagesContainer.appendChild(messageDiv);
        scrollToBottom();
        
        // Add to conversation history
        if (sender === 'user') {
            conversationHistory.push({ role: 'user', content: text });
        } else if (sender === 'assistant') {
            conversationHistory.push({ role: 'assistant', content: text });
        }
    }

    // Add a status message
    function addStatusMessage(text) {
        const statusDiv = document.createElement('div');
        statusDiv.classList.add('status-message');
        statusDiv.textContent = text;
        messagesContainer.appendChild(statusDiv);
        scrollToBottom();
    }

    // Update or create assistant message for streaming
    let currentAssistantMessage = null;
    let currentAssistantContent = '';
    function updateOrCreateAssistantMessage(token) {
        if (!token) return;
        
        currentAssistantContent += token;
        
        if (!currentAssistantMessage) {
            currentAssistantMessage = document.createElement('div');
            currentAssistantMessage.classList.add('message', 'assistant');
            messagesContainer.appendChild(currentAssistantMessage);
        }
        
        currentAssistantMessage.textContent = currentAssistantContent;
        scrollToBottom();
    }

    // Play audio response
    async function playNextInQueue() {
        if (audioQueue.length === 0) {
            isPlaying = false;
            
            // Add the assistant message to the conversation history
            if (currentAssistantContent) {
                conversationHistory.push({ role: 'assistant', content: currentAssistantContent });
                currentAssistantContent = '';
            }
            
            // Reset current assistant message after finishing audio
            currentAssistantMessage = null;
            return;
        }
        
        isPlaying = true;
        const blob = audioQueue.shift();
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        
        try {
            console.log("Playing audio response");
            await new Promise((resolve, reject) => {
                audio.onended = resolve;
                audio.onerror = reject;
                audio.play().catch(reject);
            });
        } catch (err) {
            console.error('Error playing audio:', err);
            reportError(`Audio playback error: ${err.message}`);
        } finally {
            URL.revokeObjectURL(url);
            playNextInQueue();
        }
    }

    // Scroll chat to bottom
    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    // Cleanup resources
    function cleanup() {
        console.log("Cleaning up resources");
        
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
        }
        
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.close();
        }
        
        isRecording = false;
        toggleButton.textContent = 'Start Conversation';
        toggleButton.classList.remove('recording');
        recordingIndicator.classList.remove('active');
        
        const vuMeterLevel = document.getElementById('vu-meter-level');
        if (vuMeterLevel) {
            vuMeterLevel.style.width = '0%';
        }
    }

    // Initialize the app
    toggleButton.addEventListener('click', toggleRecording);

    // Handle page visibility change to reconnect if needed
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && (!ws || ws.readyState !== WebSocket.OPEN)) {
            if (!isRecording) {
                addStatusMessage("Page visible again. Reconnecting...");
                initializeWebSocket();
            }
        }
    });

    // Handle page unload
    window.addEventListener('beforeunload', cleanup);
});