import asyncio
import numpy as np
import sounddevice as sd

class Recorder:
    def __init__(self):
        # we defer samplerate & dtype until record() is called
        self._frames: list[np.ndarray] = []

    async def record(
        self,
        samplerate: int,
        dtype: str,
        channels: int = 1
    ) -> np.ndarray:
        """
        Record from the default audio input until ENTER is pressed.
        
        :param samplerate: e.g. 16000 or 24000
        :param dtype:      one of 'int16', 'float32', 'uint8', etc.
        :param channels:   number of audio channels (1=mono, 2=stereo)
        :return:           1‑D NumPy array of shape (num_samples * channels,)
        """
        self._frames.clear()

        def _callback(indata, *_):
            # indata is a 2D array shape (frames_per_buffer, channels), dtype as requested
            self._frames.append(indata.copy())

        with sd.InputStream(
            samplerate=samplerate,
            channels=channels,
            dtype=dtype,
            callback=_callback
        ):
            loop = asyncio.get_running_loop()
            # offload blocking input() to a thread
            await loop.run_in_executor(None, input)

        # concatenate all buffers along the time axis, then flatten channels
        audio = np.concatenate(self._frames, axis=0).flatten()
        return audio

# ─── Example usage ─────────────────────────────────────────────────────────────

async def main():
    print("[🎙️] Recording… Press ENTER to stop.")
    recorder = Recorder()
    audio_data = await recorder.record(samplerate=16000, dtype='float32')

    print("[🔊] Playing… Press ENTER to stop.")
    sd.play(audio_data, 16000); sd.wait()

if __name__ == "__main__":
    asyncio.run(main())
