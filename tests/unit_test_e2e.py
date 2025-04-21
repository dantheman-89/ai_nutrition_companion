import asyncio
import os
import sys
import numpy as np
import wave
import miniaudio  # for audio playback
import time
from app.utils.audio_record import Recorder

# load AI models
start_load = time.perf_counter()

from app.asr.asr import transcribe_audio
from app.services.llm import stream_chat_completion, system_prompt
from app.services.tts import synthesize_speech

load_duration = time.perf_counter() - start_load
print(f"Models loaded in {load_duration:.3f} seconds")

# funciton to run ASR, LLM and TTS pipeline
async def run_pipeline(audio_bytes: bytes, label: str):
    # ASR
    print("[🔠] Transcribing...")
    start_asr = time.perf_counter()
    transcription = await transcribe_audio(audio_bytes)
    print(f"[🗣️] You said: {transcription}")
    asr_duration = time.perf_counter() - start_asr
    print(f"asr completed in {asr_duration:.3f} seconds")

    # LLM
    messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcription}
        ]

    print("[🤖] Thinking...")
    start_llm = time.perf_counter()
    reply = ""
    async for token in stream_chat_completion(messages):
        print(token, end="", flush=True)
        reply += token
    llm_duration = time.perf_counter() - start_llm
    print(f"LLM completed in {llm_duration:.3f} seconds")

    # TTS
    print("\n[🧠] Synthesizing...")
    start_tts = time.perf_counter()
    audio = await synthesize_speech(reply)
    tts_duration = time.perf_counter() - start_tts
    print(f"TTS completed in {tts_duration:.3f} seconds")

    # total time
    total_duration = time.perf_counter() - start_asr
    print(f"responded in {total_duration:.3f} seconds")

    # Play the audio directly from the in-memory bytes.
    play_audio_from_bytes(audio)

     # Save the audio output
    output_path = f"generated\{label}_output.mp3"
    with open(output_path, "wb") as f:
        f.write(audio)
    print(f"[💾] Saved response to: {output_path}")

def main():
    mode = input("Choose input mode:\n1. Pre-recorded (input_audio.wav)\n2. Live mic input\nEnter 1 or 2: ").strip()
    if mode == "1":
        audio_path = "tests\input_audio.wav"
        if not os.path.exists(audio_path):
            print(f"File '{audio_path}' not found.")
            sys.exit(1)
    elif mode == "2":
        audio_path = record_until_enter()
    else:
        print("Invalid input. Please enter 1 or 2.")
        sys.exit(1)

    audio_bytes = load_wav_as_bytes(audio_path)
    asyncio.run(run_pipeline(audio_bytes, label="live" if mode == "2" else "file"))


if __name__ == "__main__":
    main()