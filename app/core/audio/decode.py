import numpy as np
import ffmpeg
import io

def decode_audio(audio_bytes: bytes, sample_rate: int = 16000) -> np.ndarray:
    """
    Convert input audio bytes to a mono float32 NumPy array using ffmpeg.
    Handles WebM/Opus format from browser's MediaRecorder.
    Output shape: (num_samples,)
    """
    try:
        # Create an in-memory buffer
        buffer = io.BytesIO(audio_bytes)
        
        # Use ffmpeg to decode WebM to raw PCM
        out, _ = (
            ffmpeg
            .input('pipe:')  # Read from stdin
            .output('pipe:', format='f32le', acodec='pcm_f32le', ac=1, ar=str(sample_rate))
            .run(input=buffer.read(), capture_stdout=True, capture_stderr=True)
        )
        
        # Convert to numpy array
        audio_np = np.frombuffer(out, np.float32)
        
        # Normalize if needed (WebM audio might need normalization)
        if audio_np.max() > 1.0 or audio_np.min() < -1.0:
            audio_np = np.clip(audio_np / max(abs(audio_np.max()), abs(audio_np.min())), -1.0, 1.0)
            
        return audio_np
        
    except ffmpeg.Error as e:
        print(f"FFmpeg error: {e.stderr.decode()}")
        return np.array([], dtype=np.float32)
    except Exception as e:
        print(f"Error decoding audio: {e}")
        return np.array([], dtype=np.float32)