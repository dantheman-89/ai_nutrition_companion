import asyncio
import base64
import json
import pathlib

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

from openai import AsyncOpenAI
from openai.types.beta.realtime.session import Session
from config import SYSTEM_PROMPT, OPENAI_API_KEY

from app.core.audio.convert import convert_audio_to_mp3

# ─────────────────────────────────────────────────────────────────────────────
# Setup OpenAPI client
# ─────────────────────────────────────────────────────────────────────────────
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


class RealtimeSession:
    """
    Manages the connection to OpenAI's Realtime API and handles the
    bidirectional communication between the client and OpenAI.
    """
    def __init__(self, websocket: WebSocket):
        """Initialize with a WebSocket connection."""
        self.websocket = websocket
        self.connection = None
        self.ping_task = None
        # Add these for debugging
        self.audio_chunks = []
        self.recording_start_time = None
        self.debug_save_timer = None
        
    async def setup_connection(self):
        """Establish and configure the connection to OpenAI's Realtime API."""
        # Return the connection manager to be used with async with
        return client.beta.realtime.connect(model=MODEL)
    
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
    

    async def handle_client_events(self):
        """
        Listen for messages from the client and process them.
        This function runs as a separate task.
        """
        try:
            while True:
                # Wait for the next message from the client
                msg = await self.websocket.receive()
                
                if "text" in msg:
                    try:
                        data = json.loads(msg.get("text"))
                        msg_type = data.get("type")
                        text = data.get("text", "")
                        
                        if msg_type == "user_message" and text != "":                           
                            # Send text message to OpenAI
                            await self.connection.conversation.item.create(
                                item={
                                    "type": "message",
                                    "role": "user",
                                    "content": [
                                        {"type": "input_text", "text": text}
                                    ],
                                }
                            )
                            # Generate a response
                            await self.connection.response.create()
                    
                    except json.JSONDecodeError:
                        print(f"Invalid JSON received")
                
                elif "bytes" in msg:
                    # Process audio bytes from client - no need to check recording state
                    # since client only sends bytes when recording is active
                    try:
                        # Get raw audio bytes already in pcm16 format
                        audio_bytes = msg["bytes"]

                        # Base64 encode and send to OpenAI
                        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
                        await self.connection.input_audio_buffer.append(audio=audio_base64)
                        
                    except Exception as e:
                        print(f"Error processing audio chunk: {e}")
                        import traceback
                        traceback.print_exc()
                    
        except WebSocketDisconnect:
            print("Client disconnected")
        except asyncio.CancelledError:
            print("Receive task cancelled")
        except Exception as e:
            print(f"Error in recv_from_client: {e}")
            import traceback
            traceback.print_exc()

    async def handle_openai_events(self):
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
                
                elif event.type == "response.text.delta":
                    # Handle text delta events
                    print(f"⟵ event: {event.type}, delta: {event.delta}")
                    await self.websocket.send_json({
                        "type": "text_delta",
                        "content": event.delta
                    })
                
                elif event.type in ("response.text.done", "response.done", "response.audio.done", "response.audio_transcript.done"):
                    # Handle completion events
                    print(f"⟵ event: {event.type}")
                    await self.websocket.send_json({
                        "type": "done",
                        "content": ""
                    })

                elif event.type == "error":
                    # Handle error events
                    print(f"⟵ Error event: {event}")
                    await self.websocket.send_json({
                        "type": "error",
                        "message": f"API error: {event.error.message if hasattr(event, 'error') else 'Unknown error'}"
                    })
                
                else:
                    # Log other event types
                    print(f"⟵ event: {event}")
                    
        except asyncio.CancelledError:
            print("Send task cancelled")
        except Exception as e:
            print(f"Error in send_to_client: {e}")
            import traceback
            traceback.print_exc()

@app.websocket("/ws")
async def realtime_ws(ws: WebSocket):
    """
    Handle WebSocket connections and manage the realtime session.
    """
    await ws.accept()
    print("WebSocket connection accepted")
    
    session = RealtimeSession(ws)
    
    try:
        # Get the connection manager and use it with async with
        async with await session.setup_connection() as connection:
            session.connection = connection
            print("OpenAI Realtime connection established")
            
            # Configure the session to include audio modality and server VAD
            await connection.session.update(
                session=Session(
                    modalities=["text", "audio"],
                    instructions=SYSTEM_PROMPT,
                    turn_detection={"type": "server_vad"}  # Enable server-side VAD
                )
            )
            print("Session configured with server-side VAD")
            
            # Create tasks for receiving from client, sending to client, and ping
            recv_task = asyncio.create_task(session.handle_client_events())
            send_task = asyncio.create_task(session.handle_openai_events())
            ping_task = asyncio.create_task(session.ping_client())
            
            # Wait for any task to complete
            done, pending = await asyncio.wait(
                [recv_task, send_task, ping_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Print which task completed first
            for task in done:
                if task == recv_task:
                    print("Client receive task completed early")
                elif task == send_task:
                    print("Server send task completed early") 
                elif task == ping_task:
                    print("Ping task completed early")
                
                # Print exception if task failed with an error
                if task.exception():
                    print(f"Task failed with exception: {task.exception()}")
            
        
            # Cancel all pending tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    
    except Exception as e:
        print(f"WebSocket error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Connection is automatically closed by the async with context manager
        print("Closing WebSocket connection")
        await ws.close()
