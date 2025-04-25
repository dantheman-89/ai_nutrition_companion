
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