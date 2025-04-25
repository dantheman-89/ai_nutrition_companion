import asyncio
import base64
import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from openai import AsyncOpenAI
from openai.types.beta.realtime.session import Session
from openai.resources.beta.realtime.realtime import AsyncRealtimeConnection

from config import OPENAI_API_KEY, SYSTEM_PROMPT
from app.web.openai.audio_util import CHANNELS, SAMPLE_RATE, AudioPlayerAsync

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Create an instance of the AsyncOpenAI client
client = AsyncOpenAI(api_key=OPENAI_API_KEY)


class RealtimeHandler:
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.connection: Optional[AsyncRealtimeConnection] = None
        self.session: Optional[Session] = None
        self.connected = asyncio.Event()
        self.should_send_audio = asyncio.Event()
        self.last_audio_item_id = None
        self.conversation_history = []
        self.is_recording = False
        self.audio_player = AudioPlayerAsync()

    async def initialize_connection(self):
        """Initialize the connection to OpenAI Realtime API"""
        try:
            logger.info("Connecting to OpenAI Realtime API...")
            async with client.beta.realtime.connect(model="gpt-4o-realtime-preview") as conn:
                self.connection = conn
                self.connected.set()
                
                # Enable server-side Voice Activity Detection (VAD)
                logger.info("Enabling server VAD...")
                await conn.session.update(
                    session={
                        "turn_detection": {"type": "server_vad"},
                        "system_instruction": SYSTEM_PROMPT
                    }
                )
                logger.info("Server VAD enabled")
                
                # Process events from the realtime connection
                await self.handle_realtime_events(conn)
                
        except Exception as e:
            logger.error(f"Connection error: {str(e)}", exc_info=True)
            await self.websocket.send_json({"type": "status", "message": f"Connection error: {str(e)}"})
            self.connected = asyncio.Event()  # Reset the event

    async def handle_realtime_events(self, conn: AsyncRealtimeConnection):
        """Handle events from the realtime connection"""
        acc_items: Dict[str, Any] = {}

        logger.info("Starting event processing loop")
        async for event in conn:
            try:
                logger.info(f"Received event: {event.type}")
                
                if event.type == "session.created":
                    self.session = event.session
                    session_id = event.session.id or "unknown"
                    logger.info(f"Session created: {session_id}")
                    await self.websocket.send_json({
                        "type": "session.created",
                        "session_id": session_id
                    })

                elif event.type == "session.updated":
                    self.session = event.session
                    logger.info("Session updated")

                elif event.type == "response.audio.delta":
                    if event.item_id != self.last_audio_item_id:
                        self.audio_player.reset_frame_count()
                        self.last_audio_item_id = event.item_id
                        logger.info(f"New audio item: {event.item_id}")

                    # Send the audio data to the client
                    bytes_data = base64.b64decode(event.delta)
                    await self.websocket.send_bytes(bytes_data)
                    logger.debug(f"Sent audio data: {len(bytes_data)} bytes")

                elif event.type == "response.audio_transcript.delta":
                    try:
                        text = acc_items[event.item_id]
                    except KeyError:
                        acc_items[event.item_id] = event.delta
                    else:
                        acc_items[event.item_id] = text + event.delta

                    # Send the transcript to the client
                    logger.info(f"Assistant transcript: {event.delta}")
                    await self.websocket.send_json({
                        "type": "assistant_transcript",
                        "text": event.delta
                    })

                elif event.type == "input_audio_transcript.delta":
                    # Send user transcript to client
                    logger.info(f"User transcript: {event.delta}")
                    await self.websocket.send_json({
                        "type": "user_transcript",
                        "text": event.delta
                    })

                elif event.type == "response.end":
                    # Mark the end of the response
                    logger.info("Response ended")
                    currentAssistantMessage = acc_items.get(event.item_id, "")
                    if currentAssistantMessage:
                        # Save to conversation history
                        self.conversation_history.append({
                            "role": "assistant",
                            "content": currentAssistantMessage
                        })

            except Exception as e:
                logger.error(f"Error processing event: {str(e)}", exc_info=True)
                await self.websocket.send_json({"type": "error", "message": str(e)})

    async def process_audio(self, audio_data: bytes):
        """Process audio data from the client"""
        if not self.connected.is_set():
            logger.warning("Trying to process audio but not connected yet")
            return

        try:
            # Send audio data to the OpenAI Realtime API
            connection = self.connection
            if connection:
                # Convert to base64
                audio_b64 = base64.b64encode(audio_data).decode("utf-8")
                logger.debug(f"Processing audio data: {len(audio_data)} bytes")
                await connection.input_audio_buffer.append(audio=audio_b64)
        except Exception as e:
            logger.error(f"Error processing audio: {str(e)}", exc_info=True)
            await self.websocket.send_json({"type": "error", "message": f"Error processing audio: {str(e)}"})

    async def stop_recording(self):
        """Stop recording and let the model respond"""
        if not self.connected.is_set() or not self.connection:
            logger.warning("Trying to stop recording but not connected")
            return

        try:
            logger.info("Stopping recording")
            # If manual VAD mode is enabled, commit the buffer and create response
            if self.session and self.session.turn_detection is None:
                logger.info("Manual VAD mode - committing buffer")
                await self.connection.input_audio_buffer.commit()
                await self.connection.response.create()
        except Exception as e:
            logger.error(f"Error stopping recording: {str(e)}", exc_info=True)
            await self.websocket.send_json({
                "type": "error", 
                "message": f"Error stopping recording: {str(e)}"
            })


@app.get("/")
async def index():
    """Serve the index.html file"""
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for the realtime conversation"""
    await websocket.accept()
    logger.info("WebSocket connection accepted")
    
    handler = RealtimeHandler(websocket)
    
    # Start the connection to OpenAI Realtime API
    connection_task = asyncio.create_task(handler.initialize_connection())
    
    try:
        # Process messages from the client
        logger.info("Starting WebSocket message processing loop")
        while True:
            message = await websocket.receive()
            
            if "bytes" in message:
                # Process binary audio data
                audio_data = message["bytes"]
                if audio_data:
                    handler.is_recording = True
                    logger.debug(f"Received audio data: {len(audio_data)} bytes")
                    await handler.process_audio(audio_data)
            
            elif "text" in message:
                # Process text commands
                try:
                    data = json.loads(message["text"])
                    logger.info(f"Received text command: {data}")
                    if data.get("command") == "stop":
                        handler.is_recording = False
                        await handler.stop_recording()
                    elif data.get("command") == "cancel":
                        if handler.connection:
                            await handler.connection.send({"type": "response.cancel"})
                except json.JSONDecodeError:
                    logger.error("Failed to parse JSON message")
                    pass
    
    except WebSocketDisconnect:
        # Handle disconnect
        logger.info("WebSocket disconnected")
    except Exception as e:
        # Handle other exceptions
        logger.error(f"WebSocket error: {str(e)}", exc_info=True)
    finally:
        # Clean up
        logger.info("Cleaning up connection")
        connection_task.cancel()
        try:
            await connection_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")