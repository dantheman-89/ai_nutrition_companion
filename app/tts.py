import asyncio
from elevenlabs import ElevenLabs
from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID

# Initialize the ElevenLabs client.
client = ElevenLabs(api_key=ELEVENLABS_API_KEY)


def run_speech(text: str) -> bytes:
    # This is the standalone synchronous function for speech syntehsis.
    audio_data = client.text_to_speech.convert(
        voice_id=ELEVENLABS_VOICE_ID,         # voice_id: Replace with your chosen voice ID.
        output_format="mp3_44100_128",                # output_format.
        text=text,                           # The text to synthesize.
        model_id="eleven_flash_v2_5",        # model_id: eleven_multilingual_v2.
    )

    # If audio_data is a generator (or any iterable that is not bytes), join it.
    if isinstance(audio_data, bytes):
        return audio_data
    else:
        # Join all the byte chunks
        return b"".join(audio_data)

async def synthesize_speech(text: str) -> bytes:
    """
    Asynchronously synthesize speech using the ElevenLabs TTS API.
    
    This function wraps the synchronous TTS API call in an executor so that it does not
    block the asyncio event loop.
    
    Args:
        text (str): The input text to convert to speech.
    
    Returns:
        bytes: The synthesized audio data.
    """
    loop = asyncio.get_running_loop()
    # Offload the blocking call to a thread.
    audio_data = await loop.run_in_executor(
        None,
        run_speech,
        text
    )
    return audio_data


