import asyncio
import whisper

# Load your model globally (do this once to save time on subsequent requests)
model = whisper.load_model("tiny")  # or "tiny" if you need faster response

async def transcribe_audio(audio_bytes: bytes) -> str:
    """
    Process the audio bytes using the Whisper ASR model.
    """
    # Save the audio to a temporary file (Whisper requires a file input)
    with open("temp_audio.wav", "wb") as f:
        f.write(audio_bytes)
    
    # Run the transcription (blocking call, so we run it in an executor)
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, model.transcribe, "temp_audio.wav")
    
    # Clean up temp file if needed (or you can use a BytesIO approach if supported)
    # os.remove("temp_audio.wav")
    return result.get("text", "").strip()