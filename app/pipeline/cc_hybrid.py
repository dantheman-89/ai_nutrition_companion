import asyncio
from config import SYSTEM_PROMPT
from elevenlabs import stream
import time

# Load AI models
start_load = time.perf_counter()
from app.services.asr import transcribe_audio
from app.services.llm import stream_text_response
from app.services.tts import synthesize_speech

load_duration = time.perf_counter() - start_load
print(f"Models loaded in {load_duration:.3f} seconds")

# Function to run ASR, LLM, and TTS pipeline
async def run_pipeline(audio_bytes: bytes, conversation_history: list):
    # ASR
    print("[🔠] Transcribing...")
    start_asr = time.perf_counter()
    transcription = await transcribe_audio(audio_bytes)
    print(f"[🗣️] You said: {transcription}")
    asr_duration = time.perf_counter() - start_asr
    print(f"ASR completed in {asr_duration:.3f} seconds")

    # Update conversation history with user's input
    conversation_history.append({"role": "user", "content": transcription})

    # LLM        
    print("\n[🤖] Thinking...")
    start_llm = time.perf_counter()
    reply = ""
    async for token in stream_text_response(conversation_history, SYSTEM_PROMPT):
        print(token, end="", flush=True)
        reply += token
    llm_duration = time.perf_counter() - start_llm
    print(f"\nLLM completed in {llm_duration:.3f} seconds")

    # Update conversation history with AI's response
    conversation_history.append({"role": "assistant", "content": reply})

    # TTS
    print("\n[🧠] Synthesizing...")
    start_tts = time.perf_counter()
    audio_stream = await synthesize_speech(reply)
    audio_stream = list(audio_stream)  # Convert the generator to a list (bad for streaming, but good for timing)
    tts_duration = time.perf_counter() - start_tts
    print(f"TTS completed in {tts_duration:.3f} seconds")

    # Total time
    total_duration = time.perf_counter() - start_asr
    print(f"Responded in {total_duration:.3f} seconds")

    # Play audio and wait for completion
    print("\n[🔊] Playing response...")
    await asyncio.to_thread(stream, audio_stream)
    print("\n[✅] Response complete")

    return conversation_history

async def main():
    from app.utils.audio_record import Recorder
    
    print("Starting conversation... Press Ctrl+C to exit.")
    recorder = Recorder()
    conversation_history = []  # Initialize conversation history
    
    try:
        while True:
            # Record audio live
            print("\n[🎙️] Recording… Press ENTER to stop.")
            audio_data = await recorder.record(samplerate=16000, dtype='float32')

            # Run the pipeline function and update conversation history
            conversation_history = await run_pipeline(audio_data, conversation_history)
            
            # Small pause to ensure audio playback is complete
            await asyncio.sleep(0.5)
            
    except KeyboardInterrupt:
        print("\nEnding conversation...")

if __name__ == "__main__":
    # Run the main function directly using asyncio
    asyncio.run(main())  # This runs the main function which calls the pipeline
