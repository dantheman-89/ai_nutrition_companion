import asyncio
import openai
from config import OPENAI_API_KEY

# Configure OpenAI with your API key.
openai.api_key = OPENAI_API_KEY

# Define your system prompt.
system_prompt = (
    "You are a friendly and empathetic AI companion. "
    "You are having a real time voice to voice conversation with a human needing your help on health and wellness"
    "Engage in conversation like a very likable human. "
    "Keep your answers concise, warm, and conversational as you would speak out"
    "suitable for a casual and interactive dialogue."
)

# Initialize conversation history.
messages = [
    {"role": "system", "content": system_prompt},
    # Optionally add an initial user message if needed.
    # {"role": "user", "content": "Hello"}
]

def run_stream(messages, queue, loop):
    """
    This synchronous function calls the OpenAI ChatCompletion API in streaming mode
    and pushes each token into an asyncio queue.
    """
    response = openai.ChatCompletion.create(
        model="gpt-4.1-nano",
        messages=messages,
        temperature=0.8,
        max_tokens=150,
        stream=True
    )
    for chunk in response:
        # Extract token from the delta, if available.
        token = chunk["choices"][0]["delta"].get("content", "")
        # Safely schedule putting the token on the asyncio queue.
        asyncio.run_coroutine_threadsafe(queue.put(token), loop)
    # Signal the end of the stream.
    asyncio.run_coroutine_threadsafe(queue.put(None), loop)

async def stream_chat_completion_async(messages):
    """
    Asynchronous generator that yields tokens from the streaming ChatCompletion.
    It uses an asyncio queue to pass tokens from the blocking function running in a separate thread.
    """
    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    # Run the blocking streaming function in the default thread pool executor.
    loop.run_in_executor(None, run_stream, messages, queue, loop)

    # Yield tokens from the queue as they become available.
    while True:
        token = await queue.get()
        if token is None:
            break
        yield token
