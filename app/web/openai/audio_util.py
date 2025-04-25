import asyncio
import numpy as np
import sounddevice as sd
import queue

# Audio configuration
CHANNELS = 1
SAMPLE_RATE = 16000
BLOCKSIZE = 1024
DTYPE = "int16"

class AudioPlayerAsync:
    """Async audio player for streaming audio playback."""
    
    def __init__(self):
        """Initialize the audio player."""
        self.queue = asyncio.Queue()
        self.active = True
        self._frame_count = 0
        self._stream = None
        self._task = None
        
    def reset_frame_count(self):
        """Reset the frame count."""
        self._frame_count = 0
        
    def add_data(self, data: bytes):
        """Add audio data to the playback queue."""
        if not self.active:
            return
            
        self.queue.put_nowait(data)
        
        # Start the playback task if it's not running
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._play_audio())
            
    async def _play_audio(self):
        """Play audio data from the queue."""
        try:
            while self.active:
                # Get data from the queue with a timeout
                try:
                    data = await asyncio.wait_for(self.queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    if self.queue.empty():
                        break
                    continue
                    
                # Convert bytes to numpy array
                try:
                    audio_data = np.frombuffer(data, dtype=np.int16)
                    
                    # Initialize stream if needed
                    if self._stream is None:
                        try:
                            self._stream = sd.OutputStream(
                                samplerate=SAMPLE_RATE,
                                channels=CHANNELS,
                                dtype=DTYPE,
                                callback=self._audio_callback,
                            )
                            self._stream.start()
                        except sd.PortAudioError as e:
                            print(f"Error initializing audio stream: {e}")
                            # Just skip playing audio if we can't create a stream
                            # This can happen if audio devices change during runtime
                            self.queue.task_done()
                            continue
                    
                    # Write data to the stream
                    self._stream.write(audio_data)
                    
                except Exception as e:
                    print(f"Error playing audio: {e}")
                finally:
                    self.queue.task_done()
        except asyncio.CancelledError:
            print("Audio playback task cancelled")
        except Exception as e:
            print(f"Unexpected error in audio playback: {e}")
        finally:
            self._close_stream()
    
    def _audio_callback(self, outdata, frames, time, status):
        """Callback for the audio stream."""
        if status:
            print(f"Audio callback status: {status}")
    
    def _close_stream(self):
        """Close the audio stream."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as e:
                print(f"Error closing audio stream: {e}")
            finally:
                self._stream = None
            
    def stop(self):
        """Stop the audio player."""
        self.active = False
        
        # Clear the queue
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
                self.queue.task_done()
            except (asyncio.QueueEmpty, Exception):
                pass
                
        # Cancel the playback task
        if self._task is not None and not self._task.done():
            self._task.cancel()
            
        # Close audio stream
        self._close_stream()