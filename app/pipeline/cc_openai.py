import asyncio
import base64
import time
import openai
import numpy as np
import sounddevice as sd
import io
import wave
from typing import Literal
from config import OPENAI_API_KEY, SYSTEM_PROMPT
from app.utils.audio_record import Recorder

# Configure OpenAI API key
openai.api_key = OPENAI_API_KEY

async def converse(mode: Literal['text', 'both'] = 'text') -> str:
    """
    High-level function:
    - 'text' mode: streams text response from OpenAI
    - 'both' mode: retrieves full text and audio in one call

    Returns the full text response.
    """
    recorder = Recorder()

    # 1) Record audio and base64-encode WAV
    print("[🎙️] Recording... press ENTER to stop.")
    wav_bytes = await recorder.record_wav_bytes(samplerate=24000, dtype='int16')
    wav_b64 = base64.b64encode(wav_bytes).decode('utf-8')

    # Common request fields
    model = 'gpt-4o-audio-preview'
    messages = [
        {'role': 'system', 'content': SYSTEM_PROMPT},
        {'role': 'user', 'content': [
            {'type': 'input_audio', 'input_audio': {
                'data': wav_b64,
                'format': 'wav'
            }}
        ]}
    ]

    # TEXT-ONLY STREAMING
    if mode == 'text':
        start_time = time.perf_counter()
        first = True

        # stream only text deltas
        response = openai.ChatCompletion.create(
            model=model,
            modalities=['text'],
            messages=messages,
            stream=True
        )
        full_text = ''
        for chunk in response:
            delta = chunk['choices'][0]['delta']
            text = delta.get('content', '')

            if first:
                latency = time.perf_counter() - start_time
                print(f"\n[⏱] First response in {latency:.3f}s")
                print("[🤖] AI says:", end=" ", flush=True)
                first = False

            if text:
                print(text, end='', flush=True)
                full_text += text
        print()  # newline
        return full_text

    # BOTH TEXT + AUDIO
    # non-streaming call
    final = openai.ChatCompletion.create(
        model=model,
        modalities=['text', 'audio'],
        audio={'voice': 'alloy', 'format': 'wav'},
        messages=messages,
        stream=False
    )
    choice_msg = final.choices[0].message
    print(choice_msg.annotations)

    # Extract textual content, handling None or block formats
    content = choice_msg.content  # text if present ([platform.openai.com](https://platform.openai.com/docs/api-reference/chat/create))
    if isinstance(content, str):
        full_text = content or ''
    elif isinstance(content, list):
        full_text = ''.join(
            block.get('text', '') for block in content if block.get('type') == 'text'
        )
    else:
        full_text = ''

    # Extract and play audio response
    b64_audio = choice_msg.audio.data
    wav_out = base64.b64decode(b64_audio)
    wav_io = io.BytesIO(wav_out)
    with wave.open(wav_io, 'rb') as wf:
        frames = wf.readframes(wf.getnframes())
        pcm = np.frombuffer(frames, dtype=np.int16)
        sd.play(pcm, wf.getframerate())
        sd.wait()

    print(full_text)
    return full_text

if __name__ == '__main__':
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else 'both'
    reply = asyncio.run(converse(mode=mode))
