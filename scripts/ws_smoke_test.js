const url = process.argv[2] || "ws://127.0.0.1:8000/ws";
const language = process.argv[3] || "ja";

const ws = new WebSocket(url);
const timeout = setTimeout(() => {
  console.error("timeout: no close after 15 seconds");
  try {
    ws.close();
  } finally {
    process.exitCode = 1;
  }
}, 15000);

let audioReceived = 0;
let configReceived = false;
let stoppedReceived = false;

function sendJson(payload) {
  ws.send(JSON.stringify(payload));
}

function sendSilenceChunk() {
  // 50 ms of 16 kHz mono PCM s16le: 16000 * 0.05 * 2 bytes.
  ws.send(new Uint8Array(1600));
}

ws.addEventListener("open", () => {
  console.log("> open");
});

ws.addEventListener("message", (event) => {
  const text = typeof event.data === "string" ? event.data : "";
  console.log(`< ${text}`);
  let message;
  try {
    message = JSON.parse(text);
  } catch {
    return;
  }

  if (message.type === "ready") {
    sendJson({
      type: "start",
      sample_rate: 16000,
      channels: 1,
      format: "pcm_s16le",
      language,
      task: "transcribe",
      latency_ms: 1000,
      vad_mode: "server",
    });
  }

  if (message.type === "config") {
    configReceived = true;
    sendSilenceChunk();
    sendSilenceChunk();
    sendSilenceChunk();
    sendJson({ type: "stop" });
  }

  if (message.type === "audio_received") {
    audioReceived += 1;
  }

  if (message.type === "stopped") {
    stoppedReceived = true;
  }
});

ws.addEventListener("error", (event) => {
  console.error("websocket error", event.message || event.type);
  process.exitCode = 1;
});

ws.addEventListener("close", () => {
  clearTimeout(timeout);
  console.log("> close");
  if (!configReceived || audioReceived < 1 || !stoppedReceived) {
    console.error(
      `failed: config=${configReceived} audio_received=${audioReceived} stopped=${stoppedReceived}`,
    );
    process.exitCode = 1;
    return;
  }
  console.log(`ok: config=${configReceived} audio_received=${audioReceived} stopped=${stoppedReceived}`);
});
