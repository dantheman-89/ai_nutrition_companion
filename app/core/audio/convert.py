import numpy as np
import ffmpeg
import io
from pydub import AudioSegment

# Function to convert raw PCM audio to MP3 format for browser compatibility
async def convert_audio_to_mp3(audio_data: bytes) -> bytes:
    try:
        # PCM data from OpenAI is 16-bit, 24kHz, mono
        if not audio_data:
            print("Warning: Empty audio data received")
            return b""
        
        # Convert raw PCM to AudioSegment
        audio = AudioSegment(
            data=audio_data,
            sample_width=2,  # 16-bit
            frame_rate=24000,  # 24kHz
            channels=1  # mono
        )
        
        # Export as MP3
        mp3_io = io.BytesIO()
        audio.export(mp3_io, format="mp3", bitrate="128k")
        return mp3_io.getvalue()
        
    except Exception as e:
        print(f"Error converting audio: {e}")
        return b""


def convert_audio_from_WebM(audio_bytes: bytes, sample_rate: int = 24000, out_format: str = 'wav') -> bytes:
                               
    buffer = io.BytesIO(audio_bytes)

    out, err = (
        ffmpeg
        .input(
            'pipe:', 
            f='webm',
            err_detect='aggressive',   # aggressive error detection
            max_delay='500000'         # max demux delay in microseconds
        )
        .output(
            'pipe:', 
            format=out_format,          # output format (e.g. 'wav', 'f32le', f16le)
            acodec='pcm_s16le',         # 16-bit PCM (WAV default) 
            ac=1,                       # mono
            ar=str(sample_rate)         # e.g. '24000'
        )
        .global_args(
            '-y',                        # overwrite output
            '-hide_banner',
            '-loglevel', 'error'         # show errors only
        )
        .run(
            input=buffer.read(),
            capture_stdout=True,
            capture_stderr=True
        )
    )
    return out


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