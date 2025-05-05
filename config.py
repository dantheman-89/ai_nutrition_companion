# config.py
import os
from dotenv import load_dotenv

# Load environment variables from a .env file in the project root
load_dotenv()

# Retrieve your API key (it will be None if not set)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LINKAI_API_KEY = os.getenv("LINKAI_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")

# Gmail Information
# Gmail开启SMTP参考https://www.cnblogs.com/jiyuwu/p/16313476.html
SMTP_SERVER = os.getenv("SMTP_SERVER")  ## e.g. smtp.gmail.com
SMTP_PORT = os.getenv("SMTP_PORT")  ## 587
SMTP_USERNAME = os.getenv("SMTP_USERNAME") ## xxxxxxxxx@gmail.com
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD") ## abcd efgh ijkl mnop

# VoiceID
ELEVENLABS_VOICE_ID = "56AoDkrOh6qfVPDXZ7Pt" # Cassidy
ELEVENLABS_RT_AGENT_ID = "RymawqfeH44NQriMkgGH"


# System prompt for the voice assistant
SYSTEM_PROMPT = (
    "You are a friendly and empathetic AI companion. "
    "You are having a real time voice to voice conversation with a human needing your help on health and wellness"
    "Engage in conversation like a very likable human. "
    "Keep your answers concise, warm, and conversational as you would speak out"
    "Keep your answers short, and really get to user to talk more in a very interactive and likable way."
)