import asyncio
import base64
import json
import pathlib
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
from openai import AsyncOpenAI
from openai.types.beta.realtime.session import Session, InputAudioNoiseReduction, InputAudioTranscription

from app.core.audio.convert import convert_audio_to_mp3
from config import SYSTEM_PROMPT, OPENAI_API_KEY

# ─────────────────────────────────────────────────────────────────────────────
# OpenAPI model select
# ─────────────────────────────────────────────────────────────────────────────
MODEL = "gpt-4o-mini-realtime-preview"

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
        self.client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        
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
                    # Process audio bytes from client
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

                # process response audio data
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
                
                # response transcript/text delta
                elif event.type in ("response.audio_transcript.delta", 
                                    "response.text.delta"):
                    print(f"⟵ event: {event.type}, delta: {event.delta}")
                    await self.websocket.send_json({
                        "type": "text_delta",
                        "content": event.delta
                    })
                
                # response transcript/text completed
                elif event.type in ("response.audio_transcript.done"):
                    print(f"⟵ event: {event.type}, : {event.transcript}")
                    await self.websocket.send_json({
                        "type": "text_done"
                    })

                # input transcript delta
                elif event.type in ("conversation.item.input_audio_transcription.delta"):
                    print(f"⟵ event: {event.type}, delta: {event.delta}")
                    await self.websocket.send_json({
                        "type": "input_audio_transcript_delta",
                        "content": event.delta
                    })
                
                 # input transcript completed
                elif event.type == "conversation.item.input_audio_transcription.completed":
                    print(f"⟵ event: {event.type}, : {event.transcript}")
                    await self.websocket.send_json({
                        "type": "input_audio_transcript_done"
                    })
                
                elif event.type in ("session.created",
                                    "input_audio_buffer.speech_started",
                                    "input_audio_buffer.speech_stopped",
                                    "input_audio_buffer.committed",
                                    "conversation.item.created",                                    
                                    "rate_limits.updated",
                                    "response.created",
                                    "response.output_item.added",
                                    "response.output_item.done",
                                    "response.content_part.added",
                                    "response.content_part.done",
                                    "response.audio.done",
                                    "response.done"
                                    ):
                    # print events without action required
                    print(f"⟵ event: {event.type}")

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
    
    try:
        # Start an OpenAI session
        session = RealtimeSession(ws)

        # Get the connection manager and use it with async with 
        async with session.client.beta.realtime.connect(model=MODEL) as connection:
            session.connection = connection
            print("OpenAI Realtime connection established")
            
            # Configure the session to include audio modality and server VAD
            await connection.session.update(
                session=Session(
                    modalities=["text", "audio"],
                    instructions=SYSTEM_PROMPT,
                    input_audio_noise_reduction=InputAudioNoiseReduction(type="near_field"),
                    input_audio_transcription=InputAudioTranscription(
                        language="en",  # ISO-639-1 language code, Chinese for zh or zh-CN
                        model="gpt-4o-mini-transcribe",  # Or "whisper-1" or "gpt-4o-mini-transcribe"
                        prompt="Expect technical terms related to nutrition" # Optional guidance
                    ),
                    turn_detection={"type": "server_vad"},  # Enable server-side VAD,
                    max_response_output_tokens=120
                )
            )
            print("Session configured with server-side VAD")
            
            # Create tasks for receiving from client, sending to client, and ping
            client_task = asyncio.create_task(session.handle_client_events())
            openai_task = asyncio.create_task(session.handle_openai_events())
            
            # Wait for any task to complete
            done, pending = await asyncio.wait(
                [client_task, openai_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Print which task completed first
            for task in done:
                if task == client_task:
                    print("client task completed early")
                elif task == openai_task:
                    print("OpenAI task completed early") 
        
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
