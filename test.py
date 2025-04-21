import asyncio
import time
from elevenlabs.client import ElevenLabs
from elevenlabs import stream
from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID

# Initialize the ElevenLabs client.
client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

# Function to generate speech (async)
async def run_speech_sync(text: str):
    audio_stream = client.text_to_speech.convert_as_stream(
        voice_id=ELEVENLABS_VOICE_ID,
        output_format="mp3_44100_128",
        text=text,
        model_id="eleven_flash_v2_5",
    )
    return audio_stream

# Function to play the audio (blocking)
def stream_audio(audio_stream):
        stream(audio_stream)

# Main function
async def main():
    text = "Hi there! How’s your day going? I’d love to help with that!"
    
    # Generate speech
    audio_stream = await run_speech_sync(text)

    # Convert the generator to a list (so you can reuse it)
    audio_chunks = list(audio_stream)

    # Record start time
    start_time = time.perf_counter()

    # Stream audio in a separate thread
    await asyncio.to_thread(stream_audio, audio_chunks)

    # Calculate and print the elapsed time
    duration = time.perf_counter() - start_time
    print(f"Audio streamed in {duration:.2f} seconds")

    # You can now safely iterate over audio_chunks (if needed)
    for chunk in audio_chunks:
        print("Audio chunk processed")

if __name__ == "__main__":
    asyncio.run(main())
