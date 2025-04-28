import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import PlainTextResponse, JSONResponse, RedirectResponse
from dotenv import load_dotenv
import pathlib

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

class RealtimeSession:
    """
    Manages the connection to OpenAI's Realtime API and handles the
    bidirectional communication between the client and OpenAI.
    """
    def __init__(self, websocket: WebSocket):
        """Initialize with a WebSocket connection."""
        self.websocket = websocket
        self.connection = None
        
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
                # Debug output
                print("⟵ event:", event)
                
                # Process the event based on its type
                if event.type == "response.text.delta":
                    await self.websocket.send_text(event.delta)
                elif event.type in ("response.text.done", "response.done"):
                    await self.websocket.send_text("\n")
                    
        except asyncio.CancelledError:
            print("Send task cancelled")
        except Exception as e:
            print(f"Error in send_to_client: {e}")

    async def keep_alive(self, interval):
        """Send periodic keep-alive messages to prevent connection timeout."""
        try:
            while True:
                await asyncio.sleep(interval)  # Send a ping every 5 seconds
                # Non-disruptive ping to OpenAI
                await self.connection.conversation.item.create(
                    item={
                        "type": "ping"
                    }
                )
        except asyncio.CancelledError:
            print("Keep-alive task cancelled")
        except Exception as e:
            print(f"Error in keep_alive: {e}")

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
            
            # Configure the session
            await connection.session.update(
                session=Session(
                    modalities=["text"],
                    instructions="You are a helpful AI assistant.",
                    temperature=0.8,
                )
            )
            
            # Create tasks for receiving from client and sending to client
            recv_task = asyncio.create_task(session.recv_from_client())
            send_task = asyncio.create_task(session.send_to_client())
            
            await send_task
            print('send_task completed')

            await recv_task
            print('recv_task completed')

            # Wait for either task to complete or an error
            # done, pending = await asyncio.wait(
            #     [recv_task, send_task, keep_alive_task],
            #     return_when=asyncio.FIRST_COMPLETED
            # )

            #  # Print which task completed first
            # for task in done:
            #     if task == recv_task:
            #         print("Client receive task completed early")
            #     elif task == send_task:
            #         print("OpenAI event listen and send task completed early") 

            # # Cancel pending tasks
            # for task in pending:
            #     task.cancel()
            #     try:
            #         await task
            #     except asyncio.CancelledError:
            #         pass
    
    except Exception as e:
        print(f"WebSocket error: {e}")
    
    finally:
        # Connection is automatically closed by the async with context manager
        await ws.close()
