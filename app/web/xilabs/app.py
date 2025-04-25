import asyncio
import io
import json
from pathlib import Path
import queue
import threading

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import ELEVENLABS_API_KEY, ELEVENLABS_RT_AGENT_ID
from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation
from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface

app = FastAPI()

# Mount static files
BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

@app.get("/")
async def index():
    return FileResponse(BASE_DIR / "static" / "index.html")

class WebSocketMessage:
    AUDIO = "audio"
    TEXT = "text"
    
    def __init__(self, type_: str, data: bytes | dict):
        self.type = type_
        self.data = data

class WebSocketAudioInterface(DefaultAudioInterface):
    def __init__(self, ws: WebSocket):
        super().__init__()
        self.ws = ws
        self._audio_buffer = io.BytesIO()
        self._output_queue = queue.Queue()
        self._is_active = True
        self._processor_task = None

    def output(self, audio: bytes):
        if self._is_active:
            self._output_queue.put(WebSocketMessage(WebSocketMessage.AUDIO, audio))

    async def process_queue(self):
        while self._is_active:
            try:
                # Use a short timeout to allow checking _is_active
                try:
                    msg = self._output_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                if msg.type == WebSocketMessage.AUDIO:
                    await self.ws.send_bytes(msg.data)
                else:  # TEXT
                    await self.ws.send_text(json.dumps(msg.data))
                
                self._output_queue.task_done()
            except Exception as e:
                print(f"Error processing queue: {e}")
                break

    def send_text(self, type_: str, text: str):
        """Helper method to send text messages"""
        if self._is_active:
            self._output_queue.put(WebSocketMessage(
                WebSocketMessage.TEXT, 
                {"type": type_, "text": text}
            ))

    def cleanup(self):
        """Clean up resources"""
        self._is_active = False
        # Clear the queue
        try:
            while True:
                self._output_queue.get_nowait()
        except queue.Empty:
            pass

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    
    ai_interface = WebSocketAudioInterface(ws)
    
    # Start queue processor
    processor = asyncio.create_task(ai_interface.process_queue())
    
    def on_user(text: str):
        ai_interface.send_text("user", text)

    def on_agent(text: str):
        ai_interface.send_text("agent", text)

    # Initialize conversation
    conv = Conversation(
        ElevenLabs(api_key=ELEVENLABS_API_KEY),
        ELEVENLABS_RT_AGENT_ID,
        requires_auth=True,
        audio_interface=ai_interface,
        callback_user_transcript=on_user,
        callback_agent_response=on_agent,
    )

    try:
        # Start conversation in thread pool
        await asyncio.get_event_loop().run_in_executor(None, conv.start_session)
        
        while True:
            try:
                msg = await ws.receive()
                if "bytes" in msg:
                    ai_interface._audio_buffer.write(msg["bytes"])
                elif msg.get("text") == "END":
                    break
            except Exception as e:
                print(f"Error receiving message: {e}")
                break
                
    except WebSocketDisconnect:
        print("WebSocket disconnected")
    except Exception as e:
        print(f"Error in websocket connection: {e}")
    finally:
        # Cleanup in order
        ai_interface.cleanup()
        await processor
        await ai_interface._output_queue.join()
        await asyncio.get_event_loop().run_in_executor(None, conv.end_session)
