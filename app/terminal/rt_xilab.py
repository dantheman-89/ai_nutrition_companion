import signal
from config import ELEVENLABS_API_KEY, ELEVENLABS_RT_AGENT_ID

from elevenlabs.client import ElevenLabs
from elevenlabs.conversational_ai.conversation import Conversation
from elevenlabs.conversational_ai.default_audio_interface import DefaultAudioInterface

def main():
    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    conversation = Conversation(
        client,
        ELEVENLABS_RT_AGENT_ID,
        # Assume auth is required when API_KEY is set
        requires_auth=bool(ELEVENLABS_API_KEY),
        audio_interface=DefaultAudioInterface(),
        callback_agent_response=lambda response: print(f"Agent: {response}"),
        callback_agent_response_correction=lambda original, corrected: print(f"Agent: {original} -> {corrected}"),
        callback_user_transcript=lambda transcript: print(f"User: {transcript}"),
        # callback_latency_measurement=lambda latency: print(f"Latency: {latency}ms"),
    )
    conversation.start_session()

    # Run until Ctrl+C is pressed.
    signal.signal(signal.SIGINT, lambda sig, frame: conversation.end_session())

    conversation_id = conversation.wait_for_session_end()
    print(f"Conversation ID: {conversation_id}")

if __name__ == '__main__':
    main()