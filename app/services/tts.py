import asyncio
from elevenlabs.client import ElevenLabs
from elevenlabs import stream
from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
import time

# Initialize the ElevenLabs client.
client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# async function to generate speech
async def synthesize_speech(text: str) -> bytes:
    audio_stream = client.text_to_speech.convert_as_stream(
        voice_id=ELEVENLABS_VOICE_ID,
        output_format="mp3_44100_128",
        text=text,
        model_id="eleven_flash_v2_5",
    )
    return audio_stream


# ─── Example usage ─────────────────────────────────────────────────────────────

async def main():
    # Generate speech in a separate thread
    text = "Hi there! How’s your day going? I’d love to help with that!"

    # start timing
    start_time = time.perf_counter()

    # API to call for speech synthesis
    audio_stream = await synthesize_speech(text)

    # record finish line
    audio_stream = list(audio_stream)  # Convert the generator to a list (bad for streaming, but good for timing)
    duration = time.perf_counter() - start_time
    print(f"Audio streamed in {duration:.2f} seconds")
    
    # Stream audio in a separate thread
    await asyncio.to_thread(stream, audio_stream)
        

if __name__ == "__main__":
    asyncio.run(main())