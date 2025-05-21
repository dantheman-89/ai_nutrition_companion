import asyncio
import base64
import json
import pathlib
import logging
import traceback 
from datetime import datetime
import time
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from openai import AsyncOpenAI
from openai.types.beta.realtime.session import Session, InputAudioNoiseReduction, InputAudioTranscription
from starlette.websockets import WebSocketState

from app.core.audio.convert import convert_audio_to_mp3
from config import SYSTEM_PROMPT, OPENAI_API_KEY
from .tools import (
    PROFILE_TOOL_DEFINITION, update_profile_json, 
    LOAD_VITALITY_DATA_TOOL_DEFINITION, load_vitality_data, 
    LOAD_HEALTHY_SWAP_TOOL_DEFINITION, load_healthy_swap,
    CALCULATE_TARGETS_TOOL_DEFINITION, calculate_daily_nutrition_targets,
    NUTRITION_LOGGER_TOOL_DEFINITION, log_meal_photos_from_filenames,
    RECOMMEND_HEALTHY_TAKEAWAY_TOOL_DEFINITION, get_takeaway_recommendations,
    SEND_PLAIN_EMAIL_TOOL_DEFINITION, send_plain_email,
    USER_PROFILE_FILENAME
)
from .send_to_client import prepare_profile_for_display, prepare_nutrition_tracking_update 
from .util import load_json_async, save_json_async

# Set up logging with timestamps and log levels
# Set up logging with timestamps and log levels
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d %(levelname)s: %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# OpenAPI inputs
# ─────────────────────────────────────────────────────────────────────────────
MODEL = "gpt-4o-mini-realtime-preview"

DATA_DIR = pathlib.Path(__file__).parent / "data"

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

# ─────────────────────────────────────────────────────────────────────────────
# Realtime session class
# ─────────────────────────────────────────────────────────────────────────────
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
        self.user_id = "test_user"
        self.user_data_dir = DATA_DIR / self.user_id

    async def load_user(self, user_id: str):
        """
        Load user profile path. For test_user, refresh the profile from the template.
        For other users, just set up the correct path.
        """
        self.user_id = user_id # Set user_id first
        self.user_data_dir = DATA_DIR / self.user_id

        if user_id == "test_user":
            # Refresh test user profile from template
            try:
                template_path = pathlib.Path(__file__).parent / "data" / "user_profile_template.json"
                user_profile_target_path = self.user_data_dir / USER_PROFILE_FILENAME
                
                # Ensure directory exists (save_json_async will also do this, but good practice)
                await asyncio.to_thread(self.user_data_dir.mkdir, parents=True, exist_ok=True)
                
                # Read the template file
                template_data = await load_json_async(template_path, default_return_type=dict)
                
                if template_data:
                    # Write template data to the user profile
                    await save_json_async(user_profile_target_path, template_data)
                    logger.info(f"Test user profile refreshed from template to {user_profile_target_path}")
                else:
                    logger.error(f"Failed to load template data from {template_path}")

            except Exception as e:
                logger.error(f"Error refreshing test user profile: {e}", exc_info=True)
        else:
            logger.info(f"User set to: {user_id}, data directory: {self.user_data_dir}")
          
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

        task_id = id(asyncio.current_task())
        logger.info(f"[CLIENT HANDLER-{task_id}] Starting client events handler")

        try:
            while True:
                # Wait for the next message from the client
                msg = await self.websocket.receive()

                try:
                    data = json.loads(msg.get("text"))
                    event_type = data.get("type")
                    payload = data.get("payload", {}) 
                    
                    # Handle client sent user_messages
                    if event_type == "user_text_message":
                        # Send text message to OpenAI
                        await self.connection.conversation.item.create(
                            item={
                                "type": "message",
                                "role": "user",
                                "content": [
                                    {"type": "input_text", "text": payload.get("text")}
                                ],
                            }
                        )
                        # Generate a response
                        await self.connection.response.create()

                    elif event_type == "user_audio_chunk":
                        audio_base64 = payload.get("audio")
                        if audio_base64 and self.connection:
                            await self.connection.input_audio_buffer.append(audio=audio_base64) # no more encoding required as base64 encoding was done client side
                        else:
                            logger.warning(f"No audio data or no OpenAI connection for audio_chunk message.")

                    # Handle client sent meal photos nutrition estimation request
                    elif event_type == "estimate_photos_nutrition": 
                        filenames = payload.get("filenames", [])
                        if filenames:
                            logger.info(f"[CLIENT HANDLER-{task_id}] Received estimate_photos_by_name for: {filenames}")
                            asyncio.create_task(self.handle_photo_estimation_request(filenames))
                        else:
                            logger.warning("[CLIENT HANDLER-{task_id}] estimate_photos_by_name received with no filenames.")

                    # Handle client sent speech events
                    elif event_type == "speech_start":
                        logger.info(f"[CLIENT HANDLER-{task_id}] Speech start signal received")
                        # no action required
                        pass
                    
                    # commit audio buffer to finalize speech input
                    elif event_type == "speech_end":
                        # Commit audio buffer to finalize speech input
                        await self.connection.input_audio_buffer.commit()
                        # Generate a response
                        await self.connection.response.create()

                    # unhandled event
                    else:
                        logger.warning(f"[CLIENT HANDLER-{task_id}] Unknown message type received: {event_type}")

                except json.JSONDecodeError:
                    logger.error(f"[CLIENT HANDLER-{task_id}] Invalid JSON received: {msg['text']}")
                except Exception as e:
                    logger.error(f"[CLIENT HANDLER-{task_id}] Error processing client text message: {e}", exc_info=True)
                
                    
        except (WebSocketDisconnect, RuntimeError):
            print("Client disconnected  (WebSocketDisconnect or RuntimeError)")
        except asyncio.CancelledError:
            print("Receive task cancelled")
            raise
        except Exception as e:
            print(f"Error in recv_from_client: {e}")
            traceback.print_exc()
            
    async def handle_photo_estimation_request(self, filenames: list[str]):
        """Handles the background processing of photo filenames for nutrition estimation."""
        logger.info(f"Handling photo estimation request for filenames: {filenames}")
        try:
            # 1. Process photos and update profile
            tool_output = await log_meal_photos_from_filenames(self.user_data_dir, filenames) #includes an asyncio.sleep(2) for simulated delay.
            
            # 2. Send the nutrition tracking update to the client UI
            updated_profile_dict = tool_output.get("updated_full_profile")

            nutrition_payload_for_client = await prepare_nutrition_tracking_update(updated_profile_dict)
            await self.websocket.send_json({
                "type": "nutrition_tracking_update",
                "data": nutrition_payload_for_client
            })
            logger.info("Sent nutrition_tracking_update to client after photo estimation.")
            
            # 3. Send info to LLM by simulating a tool call and its output
            summary_for_ai = tool_output.get("summary_for_ai", "Meal logging process completed.")

            # Generate a unique call_id for this simulated tool interaction
            simulated_call_id = f"photolog_tool_call_{int(time.time())}"
            tool_name_for_call = NUTRITION_LOGGER_TOOL_DEFINITION["name"]

            # Create the "function_call" item in the conversation
            await self.connection.conversation.item.create(
                item={
                    "type": "function_call",
                    "call_id": simulated_call_id,
                    "name": tool_name_for_call,
                    "arguments": "{}" # No arguments needed for this simulated call
                }
            )

            # Create the "function_call_output" item with the result
            await self.connection.conversation.item.create(
                item={
                    "type": "function_call_output",
                    "call_id": simulated_call_id,
                    "output": json.dumps({"summary": summary_for_ai}) # Tool output should be a JSON string
                }
            )
            
            # Ask OpenAI to generate a response based on this new information
            await self.connection.response.create()
            logger.info("Requested OpenAI response after simulated photo log tool interaction.")

        except Exception as e:
            logger.error(f"Error in handle_photo_estimation_request: {e}", exc_info=True)
            await self.websocket.send_json({
                "type": "photo_estimation_error", 
                "message": f"Error processing photo estimation: {str(e)}"
            })


    async def handle_openai_events(self):
        """
        Stream responses from OpenAI back to the client.
        This function runs as a separate task.
        """
        task_id = id(asyncio.current_task())
        logger.debug(f"[OPENAI HANDLER-{task_id}] Starting OpenAI events handler")
        try:
            # Stream the response back to the client
            async for event in self.connection:  
                # Process the event based on its type
                start_time = time.perf_counter()
                logger.debug(f"[OPENAI HANDLER-{task_id}] Received event: {event.type}")

                current_time = datetime.now().strftime('%H:%M:%S') # Get current time

                # process response audio data
                if event.type == "response.audio.delta":
                    # Handle audio delta events
                    bytes_length = len(event.delta) if hasattr(event, 'delta') else 0
                    print(f"⟵ event ({current_time}): {event.type} (bytes: {bytes_length})") # Modified print
                    
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
                        traceback.print_exc()
                
                # response transcript/text delta
                elif event.type in ("response.audio_transcript.delta", 
                                    "response.text.delta"):
                    print(f"⟵ event ({current_time}): {event.type}, delta: {event.delta}") # Modified print
                    await self.websocket.send_json({
                        "type": "text_delta",
                        "content": event.delta
                    })
                
                # response transcript/text completed
                elif event.type in ("response.audio_transcript.done"):
                    print(f"⟵ event ({current_time}): {event.type}, : {event.transcript}") # Modified print
                    await self.websocket.send_json({
                        "type": "text_done"
                    })

                # input transcript delta
                elif event.type in ("conversation.item.input_audio_transcription.delta"):
                    print(f"⟵ event ({current_time}): {event.type}, delta: {event.delta}") # Modified print
                    await self.websocket.send_json({
                        "type": "input_audio_transcript_delta",
                        "content": event.delta
                    })
                
                 # input transcript completed
                elif event.type == "conversation.item.input_audio_transcription.completed":
                    print(f"⟵ event ({current_time}): {event.type}, : {event.transcript}") # Modified print
                    await self.websocket.send_json({
                        "type": "input_audio_transcript_done"
                    })

                # user audio completed event, sent to the client end so it can manage incoming user audio transcript
                elif event.type == "input_audio_buffer.committed":
                    print(f"⟵ event ({current_time}): {event.type}") # Modified print
                    await self.websocket.send_json({
                        "type": "input_audio_buffer_committed"
                    })

              # respond to function call
                elif event.type == "response.function_call_arguments.done":
                    print(f"⟵ event ({current_time}): {event.type}, call_id: {event.call_id}, name: {event.name}, arguments: {event.arguments}") # Modified print
                    
                    # Strip trailing parentheses if present to normalize the function name
                    base_function_name = event.name.rstrip("()")
                    _output = None

                    # do not respond to user generated function calls to send info to LLM
                    if base_function_name in ["nutrition_logger_tool"]:
                        pass
                    else:                        
                        try:
                            # --- Respond based on the function name ---
                            if base_function_name == PROFILE_TOOL_DEFINITION["name"]:
                                # Call the helper function to update the profile
                                _output = await update_profile_json(
                                    user_data_dir=self.user_data_dir, 
                                    fields_to_update=json.loads(event.arguments)
                                )
                                
                            elif base_function_name == LOAD_VITALITY_DATA_TOOL_DEFINITION["name"]:
                                # Call the helper function to load health data
                                _output = await load_vitality_data(
                                    user_data_dir=self.user_data_dir
                                )
                                
                            elif base_function_name == CALCULATE_TARGETS_TOOL_DEFINITION["name"]:
                                # Calculate nutrition targets based on profile data
                                _output = await calculate_daily_nutrition_targets(
                                    user_data_dir=self.user_data_dir
                                )
                                
                            elif base_function_name == LOAD_HEALTHY_SWAP_TOOL_DEFINITION["name"]:
                                # Load healthy swap data
                                _output = await load_healthy_swap(
                                    user_data_dir=self.user_data_dir
                                )

                            elif base_function_name == RECOMMEND_HEALTHY_TAKEAWAY_TOOL_DEFINITION["name"]:
                                # Get Takeaway recommendations
                                tool_args = json.loads(event.arguments)
                                _output = await get_takeaway_recommendations(
                                    user_data_dir=self.user_data_dir,
                                    dietary_preferences=tool_args.get("dietary_preferences"),
                                    number_of_options=tool_args.get("number_of_options", 2)
                                )

                            elif base_function_name == SEND_PLAIN_EMAIL_TOOL_DEFINITION["name"]:
                                tool_args = json.loads(event.arguments) 
                                _output = await send_plain_email( # Call the new function
                                    email_address=tool_args.get("email_address"),
                                    subject=tool_args.get("subject"),
                                    body=tool_args.get("body") # New parameter
                                )

                            else:
                                _output = json.dumps({
                                    "status": "error", 
                                    "message": f"Unknown function: {event.name}"
                                })
                                print(f"Unknown function called: {event.name}")
                            
                        except Exception as e:
                            error_message = f"Error executing function call '{event.name}': {e}"
                            print(error_message)
                            traceback.print_exc() # Print full traceback for debugging
                            _output = json.dumps({"status": "error", "message": error_message})
                        
                    # --- Send the result back to OpenAI ---
                    try:
                        if _output is not None:  # Ensure we have an output to send
                            await self.connection.conversation.item.create(
                                item={
                                    "type": "function_call_output",
                                    "call_id": event.call_id,
                                    "output": _output
                                }
                            )
                            # Generate a response
                            await self.connection.response.create()
                            print(f"function call output sent: {event.call_id}, output: {_output}") 
                    except Exception as send_error:
                        print(f"Error sending tool result back to OpenAI: {send_error}")
                        traceback.print_exc() # Print full traceback for debugging

                    # --- Send function results to the front end to display ---
                    if base_function_name in [PROFILE_TOOL_DEFINITION["name"], LOAD_VITALITY_DATA_TOOL_DEFINITION["name"], CALCULATE_TARGETS_TOOL_DEFINITION["name"]]:
                        profile_display_data = await prepare_profile_for_display(self.user_data_dir)
                        if profile_display_data: # Check if not empty            
                            await self.websocket.send_json({
                                "type": "profile_update",
                                "data": profile_display_data 
                            })
                            print(f"Sent formatted profile_update to client after {base_function_name}")
                        else:
                            print(f"No profile data to display after {base_function_name}, or profile file was empty/invalid.")
                    
                    elif base_function_name in [RECOMMEND_HEALTHY_TAKEAWAY_TOOL_DEFINITION["name"]]:
                        if _output:
                            try:
                                # _output from the tool is a JSON string like:
                                tool_result_data = json.loads(_output)
                                sent_to_client = tool_result_data.get("recommendations", [])
                                
                                # Send only the recommendations array to the client for UI rendering
                                await self.websocket.send_json({
                                    "type": "takeaway_recommendation",
                                    "payload": {"recommendations": sent_to_client} # No summary_text here
                                })
                                logger.info(f"Sent takeaway_recommendation (recommendations only) to client.")
                            except Exception as e_send:
                                logger.error(f"Error sending takeaway_recommendation to client: {e_send}")

                # rate_lmit update
                elif event.type in ("rate_limits.updated"):
                    print(f"⟵ event ({current_time}): {event.type}, : {event.rate_limits=}") 

                # events without action required
                elif event.type in ("session.created",
                                    "input_audio_buffer.speech_started",
                                    "input_audio_buffer.speech_stopped",
                                    "conversation.item.created",
                                    "response.created",
                                    "response.output_item.added",
                                    "response.output_item.done",
                                    "response.content_part.added",
                                    "response.content_part.done",
                                    "response.function_call_arguments.delta",
                                    "response.audio.done",
                                    "response.done"
                                    ):
                    # print events without action required
                    print(f"⟵ event ({current_time}): {event.type}") # Modified print

                elif event.type == "error":
                    # Handle error events
                    print(f"⟵ Error event ({current_time}): {event}") # Modified print
                    await self.websocket.send_json({
                        "type": "error",
                        "message": f"API error: {event.error.message if hasattr(event, 'error') else 'Unknown error'}"
                    })
                
                else:
                    # Log other event types
                    print(f"⟵ event ({current_time}): {event}") # Modified print

                # logging after processing the event
                end_time = time.perf_counter()
                elapsed = end_time - start_time
                logger.debug(f"[OPENAI HANDLER-{task_id}] Processed event {event.type} in {elapsed:.4f}s")
                    
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

    # Track resources for proper cleanup
    session = None

    try:
        # Start an OpenAI session
        session = RealtimeSession(ws)

        # Get the connection manager and use it with async with
        async with session.client.beta.realtime.connect(model=MODEL) as connection:
            session.connection = connection
            print("OpenAI Realtime connection established")

            # Send connection success message
            await ws.send_json({
                "type": "connection_status",
                "status": "connected"
            })

            # Configure the session
            await connection.session.update(
                session=Session(
                    modalities=["text", "audio"],
                    instructions=SYSTEM_PROMPT,
                    input_audio_noise_reduction=InputAudioNoiseReduction(type="near_field"),
                    input_audio_transcription=InputAudioTranscription(
                        language="en",
                        model="gpt-4o-mini-transcribe",
                        prompt=""
                    ),
                    turn_detection=None, #{"type": "semantic_vad", "eagerness": "medium"},
                    max_response_output_tokens=4096,
                    tools=[PROFILE_TOOL_DEFINITION, 
                           LOAD_VITALITY_DATA_TOOL_DEFINITION, 
                           CALCULATE_TARGETS_TOOL_DEFINITION, 
                           LOAD_HEALTHY_SWAP_TOOL_DEFINITION, 
                           NUTRITION_LOGGER_TOOL_DEFINITION,
                           RECOMMEND_HEALTHY_TAKEAWAY_TOOL_DEFINITION,
                           SEND_PLAIN_EMAIL_TOOL_DEFINITION],
                    tool_choice="auto"
                )
            )
            print("Session configured with push-to-talk")

            # Load user profile
            await session.load_user(user_id="test_user") 

            # voice intro from the AI
            await session.send_voice_intro("Hey there 👋 I’m here to support you on your nutrition journey; no judgment, no lectures, just helpful ideas.")

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
    
    except WebSocketDisconnect:
        # Handle normal client disconnection
        print("WebSocket disconnected by client")
        
    except Exception as e:
        # Handle unexpected errors
        print(f"WebSocket error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        try:
            await ws.close()
            print("Closing WebSocket connection")
        except RuntimeError:
            # WebSocket already closed
            pass
