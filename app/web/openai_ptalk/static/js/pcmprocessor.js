// PCM AudioWorklet processor for microphone capture
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 8192;
    this.sampleRate = 24000; // Match OpenAI's rate
  }

  process(inputs, outputs) {
    // Get mono input data (first channel of first input)
    const input = inputs[0]?.[0]; 
    
    if (input && input.length > 0) {
      // Send audio data to the main thread
      this.port.postMessage({
        pcmData: input
      });
    }
    
    // Return true to keep the processor alive
    return true;
  }
}

// Register the processor
registerProcessor('pcm-processor', PCMProcessor);