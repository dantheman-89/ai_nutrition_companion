import asyncio
import io
import numpy as np
import sounddevice as sd
import wave
import time

class Recorder:
    def __init__(self):
        # frames buffer for recorded chunks
        self._frames: list[np.ndarray] = []
        self._is_recording = False
        self._silence_threshold = 0.01  # Adjust this value to control sensitivity
        self._silence_duration = 0.0
        self._last_sound = 0.0
        self._initial_silence = True

    def _detect_silence(self, indata):
        """Detect if the audio chunk is silence"""
        # Calculate RMS of the audio chunk
        rms = np.sqrt(np.mean(indata**2))
        current_time = time.time()
        
        if rms > self._silence_threshold:
            self._silence_duration = 0.0
            self._last_sound = current_time
            self._initial_silence = False
            return False
        else:
            if self._initial_silence:
                # During initial silence, use 4-second threshold
                self._silence_duration = current_time - self._last_sound
                return self._silence_duration >= 4.0
            else:
                # After first sound, use 0.5-second threshold
                self._silence_duration = current_time - self._last_sound
                return self._silence_duration >= 0.5

    async def record(
        self,
        samplerate: int,
        dtype: str,
        channels: int = 1
    ) -> tuple[np.ndarray, bool]:
        """
        Record from the default audio input until silence is detected.

        :param samplerate: e.g. 16000 or 24000
        :param dtype:      one of 'int16', 'float32', etc.
        :param channels:   number of channels (1=mono, 2=stereo)
        :return:           tuple(audio_data, is_complete_silence)
                          audio_data: 1-D NumPy array shape (num_samples * channels,)
                          is_complete_silence: True if no sound was detected during recording
        """
        self._frames.clear()
        self._is_recording = True
        self._silence_duration = 0.0
        self._last_sound = time.time()
        self._initial_silence = True

        silence_event = asyncio.Event()

        def _callback(indata, *_):
            if self._is_recording:
                # indata: (frames_per_buffer, channels)
                self._frames.append(indata.copy())
                if self._detect_silence(indata):
                    self._is_recording = False
                    silence_event.set()

        with sd.InputStream(
            samplerate=samplerate,
            channels=channels,
            dtype=dtype,
            callback=_callback
        ):
            await silence_event.wait()

        if len(self._frames) == 0:
            # Return empty audio and True for complete silence
            return np.array([], dtype=dtype), True
            
        audio = np.concatenate(self._frames, axis=0).flatten()
        # Return audio data and False since we captured some sound
        return audio, self._initial_silence

    async def record_wav_bytes(
        self,
        samplerate: int,
        dtype: str = 'int16',
        channels: int = 1
    ) -> tuple[bytes, bool]:
        """
        Record audio and return in-memory WAV container bytes.

        :param samplerate: sample rate for recording and WAV header
        :param dtype:      numeric dtype to record ('int16' recommended)
        :param channels:   number of audio channels
        :return:           tuple(wav_bytes, is_complete_silence)
        """
        pcm, is_complete_silence = await self.record(samplerate, dtype, channels)
        buf = io.BytesIO()
        
        if len(pcm) == 0:
            return buf.getvalue(), True
            
        with wave.open(buf, 'wb') as wf:
            wf.setnchannels(channels)
            sampwidth = np.dtype(dtype).itemsize
            wf.setsampwidth(sampwidth)
            wf.setframerate(samplerate)
            if dtype == 'float32':
                int16 = (pcm * np.iinfo(np.int16).max).astype(np.int16)
                wf.writeframes(int16.tobytes())
            else:
                wf.writeframes(pcm.tobytes())
        return buf.getvalue(), is_complete_silence