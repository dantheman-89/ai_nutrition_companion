import numpy as np
import ffmpeg

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