let mediaRecorder;
let audioChunks = [];
let isRecording = false;
let ws;

const toggleButton = document.getElementById('toggle-recording');
const recordingIndicator = document.getElementById('recording-indicator');
const statusElement = document.getElementById('status');
const messagesContainer = document.getElementById('chat-messages');

// Initialize WebSocket connection
function initializeWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onopen = () => {
        statusElement.textContent = 'Connected';
        toggleButton.disabled = false;
    };

    ws.onclose = () => {
        statusElement.textContent = 'Disconnected';
        toggleButton.disabled = true;
    };

    ws.onmessage = async (event) => {
        const data = JSON.parse(event.data);
        
        switch (data.type) {
            case 'status':
                addStatusMessage(data.message);
                break;
            case 'transcription':
                addMessage(data.message, 'user');
                break;
            case 'token':
                updateOrCreateAssistantMessage(data.message);
                break;
            case 'audio':
                playAudioResponse(data.audio);
                break;
        }
    };
}

// Initialize audio recording
async function initializeRecording() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ 
            audio: {
                channelCount: 1,
                sampleRate: 16000
            } 
        });
        mediaRecorder = new MediaRecorder(stream, {
            mimeType: 'audio/webm;codecs=opus'
        });

        mediaRecorder.ondataavailable = (event) => {
            audioChunks.push(event.data);
        };

        mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm;codecs=opus' });
            const reader = new FileReader();
            
            reader.onload = () => {
                const base64Audio = reader.result.split(',')[1];
                ws.send(JSON.stringify({ audio: base64Audio }));
            };
            
            reader.readAsDataURL(audioBlob);
            audioChunks = [];
        };

        return true;
    } catch (error) {
        console.error('Error accessing microphone:', error);
        return false;
    }
}

// Toggle recording
async function toggleRecording() {
    if (!isRecording) {
        if (!mediaRecorder) {
            const initialized = await initializeRecording();
            if (!initialized) {
                alert('Could not access microphone');
                return;
            }
        }
        
        mediaRecorder.start();
        isRecording = true;
        toggleButton.textContent = 'Stop Recording';
        toggleButton.classList.add('recording');
        recordingIndicator.classList.add('active');
    } else {
        mediaRecorder.stop();
        isRecording = false;
        toggleButton.textContent = 'Start Recording';
        toggleButton.classList.remove('recording');
        recordingIndicator.classList.remove('active');
    }
}

// Add a message to the chat
function addMessage(text, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.classList.add('message', sender);
    messageDiv.textContent = text;
    messagesContainer.appendChild(messageDiv);
    scrollToBottom();
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
let currentAssistantMessage;
function updateOrCreateAssistantMessage(token) {
    if (!currentAssistantMessage) {
        currentAssistantMessage = document.createElement('div');
        currentAssistantMessage.classList.add('message', 'assistant');
        messagesContainer.appendChild(currentAssistantMessage);
    }
    currentAssistantMessage.textContent += token;
    scrollToBottom();
}

// Play audio response
function playAudioResponse(base64Audio) {
    const audio = new Audio(`data:audio/mp3;base64,${base64Audio}`);
    audio.play();
    currentAssistantMessage = null;  // Reset for next message
}

// Scroll chat to bottom
function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// Initialize
window.addEventListener('load', () => {
    initializeWebSocket();
    toggleButton.addEventListener('click', toggleRecording);
});