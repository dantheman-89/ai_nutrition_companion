import asyncio, time, json
import io
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from app.services import tts
from app.asr import asr
from app.services import llm

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

# In-memory conversation history (for demo purposes)
conversation_history = []

async def process_utterance(audio_buffer: bytes, websocket: WebSocket):
    """
    Process the audio buffer: run ASR, generate LLM response, produce TTS audio.
    """
    # Transcribe audio using the ASR module
    transcript = await asr.transcribe_audio(audio_buffer)
    conversation_history.append({"sender": "User", "text": transcript})
    
    # Generate a response based on transcript and conversation history
    response_text = await llm.generate_response(transcript, conversation_history)
    conversation_history.append({"sender": "Bot", "text": response_text})
    
    # Send the updated conversation history and response back to the client
    await websocket.send_text(json.dumps({
        "transcript": transcript,
        "response_text": response_text,
        "history": conversation_history
    }))
    
    # Convert response text into speech audio and stream back
    tts_audio = await tts.synthesize_speech(response_text)
    await websocket.send_bytes(tts_audio)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    audio_buffer = bytes()
    SILENCE_TIMEOUT = 0.7  # seconds of silence to trigger processing
    last_audio_time = time.time()
    
    try:
        while True:
            try:
                # Wait for incoming audio; using a short timeout to check continuously
                data = await asyncio.wait_for(websocket.receive_bytes(), timeout=0.1)
                # Update the buffer and timestamp when new audio arrives
                audio_buffer += data
                last_audio_time = time.time()
            except asyncio.TimeoutError:
                # Timeout occurred, no new audio chunk was received during this period.
                pass
            
            # Check if silence has been detected (no audio for SILENCE_TIMEOUT seconds)
            if audio_buffer and (time.time() - last_audio_time > SILENCE_TIMEOUT):
                # Process the accumulated audio buffer
                asyncio.create_task(process_utterance(audio_buffer, websocket))
                # Clear the buffer for next utterance
                audio_buffer = bytes()
    except WebSocketDisconnect:
        print("WebSocket disconnected")

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)