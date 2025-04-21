import asyncio
import openai
from typing import Literal
from config import OPENAI_API_KEY
from app.utils.audio_record import Recorder

# Configure OpenAI API key
openai.api_key = OPENAI_API_KEY

# System prompt for the voice assistant
SYSTEM_PROMPT = (
    "You are a friendly and empathetic AI companion. "
    "We’re having a live, voice‑driven conversation about health and wellness. "
    "Respond warmly and concisely, as if speaking naturally, suitable for a casual and interactive dialogue."
)

async def stream_response(
    recorder: Recorder,
    mode: Literal['text', 'both'] = 'text'
):
    """
    Records raw PCM16 audio via the recorder, sends to OpenAI Realtime Responses API,
    and yields (text_delta, audio_chunk) tuples. If mode=='text', audio_chunk is None.

    :param recorder: instance of AudioRecorder
    :param mode: 'text' for text-only, 'both' for text and audio
    """
    # 1) Capture raw PCM16 audio (24kHz int16)
    print("[🎙️] Recording… press ENTER to stop.")
    pcm = await recorder.record(samplerate=24000, dtype='int16')
    pcm_bytes = pcm.tobytes()

    # 2) Choose modalities based on requested mode
    modalities = ['text'] if mode == 'text' else ['text', 'audio']

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _producer():
        # Call the Realtime Responses API
        resp = openai.Response.create(
            model="gpt-4o-audio-preview",
            modalities=modalities,
            input_audio=pcm_bytes,
            input_audio_format="pcm16",  # 24kHz little-endian int16
            instructions=SYSTEM_PROMPT,
            stream=True
        )
        for chunk in resp:
            choice = chunk['choices'][0]['delta']
            text = choice.get('content', "")
            audio_chunk = choice.get('audio_chunk')
            # Push into the asyncio queue
            asyncio.run_coroutine_threadsafe(queue.put((text, audio_chunk)), loop)
        # Signal end of stream
        asyncio.run_coroutine_threadsafe(queue.put((None, None)), loop)

    # Offload the API call to the default thread pool
    loop.run_in_executor(None, _producer)

    # 3) Consume and yield incremental responses
    while True:
        text, audio_chunk = await queue.get()
        if text is None and audio_chunk is None:
            break
        yield text, audio_chunk

async def converse_text_only():
    """High-level helper: records voice, streams text-only response."""
    recorder = AudioRecorder()
    print("[🤖] AI says:", end=" ", flush=True)
    async for text, _ in stream_response(recorder, mode='text'):
        print(text, end="", flush=True)
    print()

async def converse_text_and_audio():
    """High-level helper: records voice, streams text and plays audio."""
    import miniaudio
    recorder = AudioRecorder()
    print("[🤖] AI says:")
    async for text, audio_chunk in stream_response(recorder, mode='both'):
        if text:
            print(text, end="", flush=True)
        if audio_chunk:
            stream = miniaudio.stream_memory(audio_chunk)
            with miniaudio.PlaybackDevice() as dev:
                dev.start(stream)

if __name__ == "__main__":
    # Choose mode:
    # asyncio.run(converse_text_only())
    asyncio.run(converse_text_and_audio())
