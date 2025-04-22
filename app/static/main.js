// static/main.js
const btn = document.getElementById("btnTalk");
const chat = document.getElementById("chat");
const canvas = document.getElementById("vuMeter");
const ctx = canvas.getContext("2d");

let ws, mediaRecorder, audioStream, analyser, dataArray;
const audioQueue = [];
let isPlaying = false;

btn.onclick = async () => {
  if (btn.disabled) return;

  btn.disabled = true;
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.binaryType = "arraybuffer";

  ws.onmessage = async ({ data }) => {
    if (typeof data === "string") {
      const msg = JSON.parse(data);
      if (msg.type === "end") {
        cleanup();
        return;
      }
      const alignment = msg.type === "user" ? "user-bubble" : "agent-bubble";
      chat.insertAdjacentHTML("beforeend", `<div class="${alignment}">${msg.text}</div>`);
      chat.scrollTop = chat.scrollHeight;
    } else {
      // Queue audio chunks for sequential playback
      audioQueue.push(new Blob([data], { type: "audio/mpeg" }));
      if (!isPlaying) {
        playNextInQueue();
      }
    }
  };

  ws.onclose = cleanup;
  ws.onerror = cleanup;

  try {
    audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const audioCtx = new AudioContext();
    const source = audioCtx.createMediaStreamSource(audioStream);
    analyser = audioCtx.createAnalyser();
    source.connect(analyser);
    dataArray = new Uint8Array(analyser.fftSize);

    // Start VU meter animation
    (function drawMeter() {
      if (!analyser) return;
      requestAnimationFrame(drawMeter);
      analyser.getByteTimeDomainData(dataArray);
      let sum = dataArray.reduce((acc, v) => acc + (v - 128) ** 2, 0);
      const rms = Math.sqrt(sum / dataArray.length);
      const level = rms / 128;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#4F46E5";
      ctx.fillRect(0, 0, canvas.width * level, canvas.height);
    })();

    // Set up audio recording
    mediaRecorder = new MediaRecorder(audioStream);
    mediaRecorder.ondataavailable = e => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(e.data);
      }
    };
    mediaRecorder.start(250); // Send audio chunks every 250ms

    btn.textContent = "🛑 Stop";
    btn.onclick = stopRecording;
    btn.disabled = false;
  } catch (err) {
    console.error("Error accessing microphone:", err);
    cleanup();
  }
};

async function playNextInQueue() {
  if (audioQueue.length === 0) {
    isPlaying = false;
    return;
  }

  isPlaying = true;
  const blob = audioQueue.shift();
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);

  try {
    await new Promise((resolve, reject) => {
      audio.onended = resolve;
      audio.onerror = reject;
      audio.play();
    });
  } catch (err) {
    console.error("Error playing audio:", err);
  } finally {
    URL.revokeObjectURL(url);
    playNextInQueue();
  }
}

function stopRecording() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  
  btn.disabled = true;
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
  ws.send(JSON.stringify({ text: "END" }));
}

function cleanup() {
  if (audioStream) {
    audioStream.getTracks().forEach(t => t.stop());
    audioStream = null;
  }
  if (analyser) {
    analyser = null;
  }
  if (ws) {
    if (ws.readyState === WebSocket.OPEN) {
      ws.close();
    }
    ws = null;
  }
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    mediaRecorder.stop();
  }
  audioQueue.length = 0;
  isPlaying = false;
  btn.disabled = false;
  btn.textContent = "🎤 Talk to your Companion";
  btn.onclick = btn.onclick.bind(btn);
}
