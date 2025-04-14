import asyncio
import numpy as np
import ffmpeg
from io import BytesIO
from faster_whisper import WhisperModel

# Load the Whisper model once globally
model = WhisperModel("base", device="cuda", compute_type="float16")

# function that converts audio bytes to a mono float32 NumPy array using ffmpeg
def decode_audio(audio_bytes: bytes, sample_rate: int = 16000) -> np.ndarray:
    """
    Convert input audio bytes to a mono float32 NumPy array using ffmpeg.
    Output shape: (num_samples,)
    """
    out, _ = (
        ffmpeg
        .input("pipe:0")
        .output("pipe:1", format="f32le", ac=1, ar=sample_rate)
        .run(input=audio_bytes, capture_stdout=True, capture_stderr=True)
    )
    audio_np = np.frombuffer(out, np.float32)
    return audio_np

# function that runs Whisper to transcribe the audio
def run_transcription(audio_bytes: bytes) -> str:
    # This is the standalone synchronous function for transcription.
    audio_np = decode_audio(audio_bytes)
    segments, _ = model.transcribe(audio_np)
    return " ".join(segment.text for segment in segments).strip()

# the main async function that gets called to transcribe audio 
async def transcribe_audio(audio_bytes: bytes) -> str:
    loop = asyncio.get_running_loop()
    transcript = await loop.run_in_executor(None, run_transcription, audio_bytes)
    return transcript