import asyncio
import time
from app.tts import synthesize_speech

# Example async consumer.
async def main():
    text = "Hi there! How’s your day going? I’d love to help with that! Do you have any specific goals or dietary preferences in mind?"

    print("Starting TTS synthesis...")
    # time LLM response time
    start = time.perf_counter()
    audio = await synthesize_speech(text)
    response_duration = time.perf_counter() - start
    print(f"Synthesis complete, speech generated in {response_duration:.3f} seconds")

    start_write = time.perf_counter()
    with open("generated\output_async.mp3", "wb") as f:
        f.write(audio)
    write_duration = time.perf_counter() - start_write
    print(f"Audio saved as output_async.mp3. in {write_duration:.3f} seconds")

if __name__ == "__main__":
    asyncio.run(main())



