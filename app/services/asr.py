import asyncio
import numpy as np
from faster_whisper import WhisperModel

# Load the Whisper model
model = WhisperModel("base", device="cuda", compute_type="float16")

# run transcript
def run_transcription(audio_f32: np.ndarray) -> str:
    segments, _ = model.transcribe(audio_f32)
    return " ".join(seg.text for seg in segments).strip()

# async function to run transcript
async def transcribe_audio(
        audio_pcm: np.ndarray
) -> str:
    # async function to run the transcription in a thread pool
    loop = asyncio.get_running_loop()
    transcript = await loop.run_in_executor(
        None,
        run_transcription,
        audio_pcm
    )
    return transcript

# ─── Example usage ─────────────────────────────────────────────────────────────

async def main():
    # import additional libraries
    from app.utils.audio_record import Recorder
    import time

    # record audio live
    print("[🎙️] Recording… Press ENTER to stop.")
    recorder = Recorder()
    audio_data = await recorder.record(samplerate=16000, dtype='float32')

    # transribe audio
    start_asr = time.perf_counter()
    
    transcription = await transcribe_audio(audio_data)
    
    asr_duration = time.perf_counter() - start_asr
    print(f"asr completed in {asr_duration:.3f} seconds")

    # print the transcription
    print(f"[🗣️] You said: {transcription}")

if __name__ == "__main__":
    asyncio.run(main())