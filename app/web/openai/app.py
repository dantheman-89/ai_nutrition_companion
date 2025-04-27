import os
import asyncio
import base64
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import PlainTextResponse, JSONResponse, RedirectResponse
from dotenv import load_dotenv
import pathlib
from config import SYSTEM_PROMPT
import numpy as np
from pydub import AudioSegment
import io

from openai import AsyncOpenAI
from openai.types.beta.realtime.session import Session
from openai.resources.beta.realtime.realtime import AsyncRealtimeConnection

# ─────────────────────────────────────────────────────────────────────────────
# Setup OpenAPI client
# ─────────────────────────────────────────────────────────────────────────────
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = "gpt-4o-realtime-preview"
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# ─────────────────────────────────────────────────────────────────────────────
# Setup FastAPI app
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI()

app.mount(
    "/static",
    StaticFiles(directory=pathlib.Path(__file__).parent / "static", html=True),
    name="static"
)

@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")

# Function to convert raw PCM audio to MP3 format for browser compatibility
async def convert_audio_to_mp3(audio_data: bytes) -> bytes:
    try:
        # PCM data from OpenAI is 16-bit, 24kHz, mono
        if not audio_data:
            print("Warning: Empty audio data received")
            return b""
        
        # Convert raw PCM to AudioSegment (more concise than manually creating WAV)
        audio = AudioSegment(
            data=audio_data,
            sample_width=2,  # 16-bit
            frame_rate=24000,  # 24kHz
            channels=1  # mono
        )
        
        # Export as MP3
        mp3_io = io.BytesIO()
        audio.export(mp3_io, format="mp3", bitrate="128k")
        return mp3_io.getvalue()
        
    except Exception as e:
        print(f"Error converting audio: {e}")
        return b""

class RealtimeSession:
    """
    Manages the connection to OpenAI's Realtime API and handles the
    bidirectional communication between the client and OpenAI.
    """
    def __init__(self, websocket: WebSocket):
        """Initialize with a WebSocket connection."""
        self.websocket = websocket
        self.connection = None
        self.last_audio_item_id = None
        
    async def setup_connection(self):
        """Establish and configure the connection to OpenAI's Realtime API."""
        # Return the connection manager to be used with async with
        return client.beta.realtime.connect(model=MODEL)
    
    async def recv_from_client(self):
        """
        Listen for messages from the client and process them.
        This function runs as a separate task.
        """
        try:
            while True:
                # Wait for the next message from the client
                msg = await self.websocket.receive_json()
                if msg.get("type") == "user_message":
                    # Send the message to OpenAI
                    await self.connection.conversation.item.create(
                        item={
                            "type": "message",
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": msg["text"]}
                            ],
                        }
                    )
                    
                    # Tell OpenAI to start generating a response
                    await self.connection.response.create()
                    
        except WebSocketDisconnect:
            print("Client disconnected")
        except asyncio.CancelledError:
            print("Receive task cancelled")
        except Exception as e:
            print(f"Error in recv_from_client: {e}")
    
    async def send_to_client(self):
        """
        Stream responses from OpenAI back to the client.
        This function runs as a separate task.
        """
        try:
            # Stream the response back to the client
            async for event in self.connection:
                # Process the event based on its type
                if event.type == "response.audio.delta":
                    # Handle audio delta events
                    bytes_length = len(event.delta) if hasattr(event, 'delta') else 0
                    print(f"⟵ event: {event.type} (bytes: {bytes_length})")
                    
                    try:
                        # Process and send audio chunk
                        audio_bytes = base64.b64decode(event.delta)
                        mp3_data = await convert_audio_to_mp3(audio_bytes)
                        
                        if mp3_data and len(mp3_data) > 0:
                            mp3_base64 = base64.b64encode(mp3_data).decode('utf-8')
                            await self.websocket.send_json({
                                "type": "audio_chunk",
                                "format": "mp3",
                                "audio": mp3_base64
                            })
                    except Exception as e:
                        print(f"Error processing audio chunk: {e}")
                
                elif event.type == "response.audio_transcript.delta":
                    # Handle transcript delta events
                    print(f"⟵ event: {event.type}, delta: {event.delta}")
                    await self.websocket.send_json({
                        "type": "text_delta",
                        "content": event.delta
                    })
                
                elif event.type in ("response.text.done", "response.done"):
                    # Handle completion events
                    print(f"⟵ event: {event.type}")
                    await self.websocket.send_json({
                        "type": "done",
                        "content": ""
                    })
                
                else:
                    # Log other event types
                    print(f"⟵ event: {event}")
                    
        except asyncio.CancelledError:
            print("Send task cancelled")
        except Exception as e:
            print(f"Error in send_to_client: {e}")

    async def ping_client(self):
        """Send periodic pings to keep the WebSocket connection alive."""
        try:
            while True:
                await asyncio.sleep(30)  # Send ping every 30 seconds
                if self.websocket:
                    await self.websocket.send_json({"type": "ping"})
        except asyncio.CancelledError:
            # Expected when task is cancelled
            pass
        except Exception as e:
            print(f"Ping error: {e}")

@app.websocket("/ws")
async def realtime_ws(ws: WebSocket):
    """
    Handle WebSocket connections and manage the realtime session.
    """
    await ws.accept()
    
    session = RealtimeSession(ws)
    
    try:
        # Get the connection manager and use it with async with
        async with await session.setup_connection() as connection:
            session.connection = connection
            
            # Configure the session to include audio modality
            # The correct way to set modalities and audio settings
            await connection.session.update(
                session=Session(
                    modalities=["text", "audio"],
                    instructions=SYSTEM_PROMPT,
                )
            )
            
            # Create tasks for receiving from client and sending to client
            recv_task = asyncio.create_task(session.recv_from_client())
            send_task = asyncio.create_task(session.send_to_client())
            ping_task = asyncio.create_task(session.ping_client())
            
            # Wait for either task to complete or an error
            done, pending = await asyncio.wait(
                [recv_task, send_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    
    except Exception as e:
        print(f"WebSocket error: {e}")
    
    finally:
        # Connection is automatically closed by the async with context manager
        await ws.close()
