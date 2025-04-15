import asyncio
import time
from pathlib import Path

from app.asr import transcribe_audio  # Ensure this import path is correct for your project

def load_audio_file(path: Path) -> bytes:
    return path.read_bytes()

async def main():
    # Get the sample.wav file located in the same folder as this script
    audio_file = Path(__file__).parent / "input_audio.wav"
    
    if not audio_file.exists():
        print(f"Audio file not found at {audio_file}")
        return

    # Time how long it takes to load the audio file
    start_load = time.perf_counter()
    audio_bytes = load_audio_file(audio_file)
    load_duration = time.perf_counter() - start_load
    print(f"Audio loaded in {load_duration:.3f} seconds")

    # Time the transcription process
    start_transcription = time.perf_counter()
    transcription = await transcribe_audio(audio_bytes)
    transcription_duration = time.perf_counter() - start_transcription
    print(f"Transcription: {transcription}")
    print(f"Transcription took {transcription_duration:.3f} seconds")

if __name__ == "__main__":
    asyncio.run(main())
