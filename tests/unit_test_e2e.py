import asyncio
import os
import sys
import sounddevice as sd
import numpy as np
import wave
import tempfile
import threading
import miniaudio  # for audio playback

from app.asr import transcribe_audio
from app.llm import stream_chat_completion, system_prompt
from app.tts import synthesize_speech

def record_until_enter(sample_rate=16000):
    print("[🎙️] Recording... Press ENTER to stop.")
    frames = []
    recording = True

    # Thread function to monitor for ENTER key press.
    def input_thread():
        nonlocal recording
        input()  # Wait for ENTER key.
        recording = False

    thread = threading.Thread(target=input_thread)
    thread.start()

    # Callback simply appends incoming audio data.
    def callback(indata, frames_count, time, status):
        frames.append(indata.copy())

    # Open the input stream and use a loop to check the recording flag.
    with sd.InputStream(samplerate=sample_rate, channels=1, dtype=np.int16, callback=callback) as stream:
        while recording:
            sd.sleep(100)  # Check every 100ms.
        # After stop, stop the stream gracefully.
        stream.stop()

    # Concatenate all recorded frames.
    audio = np.concatenate(frames, axis=0)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
        with wave.open(f.name, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # int16 is 2 bytes.
            wf.setframerate(sample_rate)
            wf.writeframes(audio.tobytes())
        return f.name


def load_wav_as_bytes(file_path):
    with open(file_path, "rb") as f:
        return f.read()

def play_audio_from_bytes(audio_bytes: bytes):
    """
    Saves the audio bytes to a temporary MP3 file,
    then plays the file using miniaudio's stream_file and PlaybackDevice.
    """
    try:
        # Write the audio bytes to a temporary MP3 file.
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio_file:
            temp_audio_file.write(audio_bytes)
            temp_audio_file.flush()
            temp_file_name = temp_audio_file.name

        print(f"[🔊] Playing audio from temporary file: {temp_file_name}")
        stream = miniaudio.stream_file(temp_file_name)
        with miniaudio.PlaybackDevice() as device:
            device.start(stream)
            input("Audio file playing in the background. Press ENTER to stop playback: ")
    except Exception as e:
        print(f"[Error] Playback error: {e}")
    finally:
        try:
            os.remove(temp_file_name)
        except Exception:
            pass


async def run_pipeline(audio_bytes: bytes, label: str):
    print("[🔠] Transcribing...")
    transcription = await transcribe_audio(audio_bytes)
    print(f"[🗣️] You said: {transcription}")

   

    print("[🤖] Thinking...")
    reply = ""
    async for token in stream_chat_completion(messages):
        print(token, end="", flush=True)
        reply += token

    print("\n[🧠] Synthesizing...")
    audio = await synthesize_speech(reply)

    # Save the audio output
    output_path = f"generated\{label}_output.mp3"
    with open(output_path, "wb") as f:
        f.write(audio)
    print(f"[💾] Saved response to: {output_path}")

    # Playback via miniaudio
    try:
        stream = miniaudio.stream_file(output_path)
        with miniaudio.PlaybackDevice() as device:
            device.start(stream)
    except Exception as e:
        print(f"[Error] Playback error: {e}")

async def run_pipeline(audio_bytes: bytes, label: str):
    print("[🔠] Transcribing...")
    transcription = await transcribe_audio(audio_bytes)
    print(f"[🗣️] You said: {transcription}")

    messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": transcription}
        ]

    print("[🤖] Thinking...")
    reply = ""
    async for token in stream_chat_completion(messages):
        print(token, end="", flush=True)
        reply += token

    print("\n[🧠] Synthesizing...")
    audio = await synthesize_speech(reply)

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