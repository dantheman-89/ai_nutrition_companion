# config.py
import os
from dotenv import load_dotenv

# Load environment variables from a .env file in the project root
load_dotenv()

# Retrieve your API key (it will be None if not set)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")


# VoiceID
ELEVENLABS_VOICE_ID = "56AoDkrOh6qfVPDXZ7Pt" # Cassidy