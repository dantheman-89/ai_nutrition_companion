import asyncio
import io
import numpy as np
import sounddevice as sd
import wave

class Recorder:
    def __init__(self):
        # frames buffer for recorded chunks
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
        :param dtype:      one of 'int16', 'float32', etc.
        :param channels:   number of channels (1=mono, 2=stereo)
        :return:           1-D NumPy array shape (num_samples * channels,)
        """
        self._frames.clear()

        def _callback(indata, *_):
            # indata: (frames_per_buffer, channels)
            self._frames.append(indata.copy())

        with sd.InputStream(
            samplerate=samplerate,
            channels=channels,
            dtype=dtype,
            callback=_callback
        ):
            loop = asyncio.get_running_loop()
            # block on ENTER in a thread pool
            await loop.run_in_executor(None, input)

        audio = np.concatenate(self._frames, axis=0).flatten()
        return audio

    async def record_wav_bytes(
        self,
        samplerate: int,
        dtype: str = 'int16',
        channels: int = 1
    ) -> bytes:
        """
        Record audio and return in-memory WAV container bytes.

        :param samplerate: sample rate for recording and WAV header
        :param dtype:      numeric dtype to record ('int16' recommended)
        :param channels:   number of audio channels
        :return:           WAV file bytes
        """
        pcm = await self.record(samplerate, dtype, channels)
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(channels)
            # sampwidth: dtype 'int16' -> 2 bytes; 'float32' -> 4 bytes
            sampwidth = np.dtype(dtype).itemsize
            wf.setsampwidth(sampwidth)
            wf.setframerate(samplerate)
            # write raw frames
            # if float32, convert to int16 for WAV compatibility
            if dtype == 'float32':
                int16 = (pcm * np.iinfo(np.int16).max).astype(np.int16)
                wf.writeframes(int16.tobytes())
            else:
                wf.writeframes(pcm.tobytes())
        return buf.getvalue()