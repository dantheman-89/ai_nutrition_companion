import asyncio
from config import SYSTEM_PROMPT
from elevenlabs import stream
import time
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import base64
import json
from pathlib import Path
import numpy as np
from app.core.audio.decode import decode_audio

# Load AI models
start_load = time.perf_counter()
from app.core.asr import transcribe_audio
from app.core.llm import stream_text_response
from app.core.tts import synthesize_speech

load_duration = time.perf_counter() - start_load
print(f"Models loaded in {load_duration:.3f} seconds")

app = FastAPI()

# Get the directory containing this file
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"

# Mount static files with the correct absolute path
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

async def decode_frontend_audio(audio_bytes: bytes) -> np.ndarray:
    """
    Decode audio bytes from frontend's WebM format to numpy array for ASR
    """
    return decode_audio(audio_bytes, sample_rate=16000)

# Function to run ASR, LLM, and TTS pipeline
async def run_pipeline(audio_bytes: bytes, conversation_history: list, websocket: WebSocket):
    # ASR
    await websocket.send_json({"type": "status", "message": "Transcribing..."})
    start_asr = time.perf_counter()
    
    # First decode the audio from frontend
    audio_data = await decode_frontend_audio(audio_bytes)
    if len(audio_data) == 0:
        await websocket.send_json({
            "type": "status",
            "message": "Error: Could not decode audio. Please try again."
        })
        return conversation_history
        
    # Then pass the decoded audio to ASR
    transcription = await transcribe_audio(audio_data)
    asr_duration = time.perf_counter() - start_asr
    
    # Send transcription to frontend
    await websocket.send_json({
        "type": "transcription",
        "message": transcription,
        "duration": f"{asr_duration:.3f}"
    })

    # Update conversation history with user's input
    conversation_history.append({"role": "user", "content": transcription})

    # LLM        
    await websocket.send_json({"type": "status", "message": "Thinking..."})
    start_llm = time.perf_counter()
    reply = ""
    async for token in stream_text_response(conversation_history, SYSTEM_PROMPT):
        reply += token
        await websocket.send_json({"type": "token", "message": token})
    
    llm_duration = time.perf_counter() - start_llm
    await websocket.send_json({"type": "llm_complete", "duration": f"{llm_duration:.3f}"})

    # Update conversation history with AI's response
    conversation_history.append({"role": "assistant", "content": reply})

    # TTS
    await websocket.send_json({"type": "status", "message": "Synthesizing speech..."})
    start_tts = time.perf_counter()
    audio_stream = await synthesize_speech(reply)
    
    # Convert audio stream to base64
    audio_data = b"".join(list(audio_stream))
    audio_base64 = base64.b64encode(audio_data).decode('utf-8')
    
    tts_duration = time.perf_counter() - start_tts
    
    # Send audio to frontend
    await websocket.send_json({
        "type": "audio",
        "audio": audio_base64,
        "duration": f"{tts_duration:.3f}"
    })

    return conversation_history

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    conversation_history = []
    
    try:
        while True:
            # Receive audio data from the client
            data = await websocket.receive_text()
            audio_data = base64.b64decode(json.loads(data)["audio"])
            
            # Process the audio and get response
            conversation_history = await run_pipeline(audio_data, conversation_history, websocket)
            
    except WebSocketDisconnect:
        print("Client disconnected")

@app.get("/", response_class=HTMLResponse)
async def get():
    html_file = STATIC_DIR / "index.html"
    return html_file.read_text()
