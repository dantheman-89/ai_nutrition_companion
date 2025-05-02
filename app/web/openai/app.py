import asyncio
import base64
import json
import pathlib
import logging
import io

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

    async def send_voice_intro(self, intro_text: str):
        """Generates TTS audio, sends it, adds text to history, and sends text delta + done."""
        print(f"Generating voice intro: '{intro_text}'")
        try:
            # 1. Generate speech using TTS API
            response = await self.client.audio.speech.create(
                model="tts-1",
                voice="alloy",
                input=intro_text,
                response_format="mp3"
            )

            # 2. Read the entire audio content
            audio_content = response.read()
            print(f"Generated intro audio size: {len(audio_content)} bytes")

            # 3. Base64 encode the entire content
            mp3_base64 = base64.b64encode(audio_content).decode('utf-8')

            # 4. Send the entire audio file in one message
            print("Sending entire intro audio file...")
            await self.websocket.send_json({
                "type": "audio_chunk",
                "format": "mp3",
                "audio": mp3_base64 # Send full base64 string
            })

            # 5. Add the intro text to the conversation history as the assistant
            print("Adding intro text to conversation history (role: assistant)")
            await self.connection.conversation.item.create(
                item={
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": intro_text}
                    ],
                }
            )

            # 6. Send the text message for display using text_delta and text_done
            print(f"Sending AI intro text delta for display: {intro_text}")
            await self.websocket.send_json({
                "type": "text_delta",
                "content": intro_text
            })
            print("Sending AI intro text_done")
            await self.websocket.send_json({
                "type": "text_done"
            })

        except Exception as tts_error:
            print(f"Error generating or sending TTS intro: {tts_error}")
            # Fallback: Send only text delta + done if TTS fails
            await self.websocket.send_json({
                "type": "text_delta",
                "content": intro_text + " (Audio intro failed)"
            })
            await self.websocket.send_json({
                "type": "text_done"
            })

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
                        # Assuming convert_audio_to_mp3 handles potential partial chunks if needed
                        mp3_data = await convert_audio_to_mp3(audio_bytes)

                        if mp3_data and len(mp3_data) > 0:
                            mp3_base64 = base64.b64encode(mp3_data).decode('utf-8')
                            await self.websocket.send_json({
                                "type": "audio_chunk",
                                "format": "mp3",
                                "audio": mp3_base64
                            })
                            # Add similar sleep here for consistency
                            await asyncio.sleep(0.025) # Prevent overwhelming client
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

                # --- Add this block ---
                elif event.type == "input_audio_buffer.committed":
                    print(f"⟵ event: {event.type}")
                    await self.websocket.send_json({
                        "type": "input_audio_buffer_committed"
                    })
                # --- End added block ---

                elif event.type in ("session.created",
                                    "input_audio_buffer.speech_started",
                                    "input_audio_buffer.speech_stopped",
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

            # Configure the session
            await connection.session.update(
                session=Session(
                    modalities=["text", "audio"],
                    instructions=SYSTEM_PROMPT,
                    input_audio_noise_reduction=InputAudioNoiseReduction(type="near_field"),
                    input_audio_transcription=InputAudioTranscription(
                        language="en",
                        model="gpt-4o-mini-transcribe",
                        prompt="Expect technical terms related to nutrition"
                    ),
                    turn_detection={"type": "semantic_vad", "eagerness": "medium"},
                    max_response_output_tokens=1024
                )
            )
            print("Session configured with server-side VAD")

            # --- Call the voice intro method ---
            await session.send_voice_intro("Hey there 👋 I’m here to support you on your nutrition journey; no judgment, no lectures, just helpful ideas.")
            # --- End call ---

            # Create tasks for handling events
            client_task = asyncio.create_task(session.handle_client_events())
            openai_task = asyncio.create_task(session.handle_openai_events())

            # Wait for tasks
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
