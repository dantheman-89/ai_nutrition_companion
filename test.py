import miniaudio
stream = miniaudio.stream_file("generated/file_output.mp3")
with miniaudio.PlaybackDevice() as device:
    device.start(stream)
    input("Audio file playing in the background. Enter to stop playback: ")