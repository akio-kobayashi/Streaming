const TARGET_SAMPLE_RATE = 16000;

const els = {
  serverUrl: document.querySelector("#serverUrl"),
  language: document.querySelector("#language"),
  latencyMs: document.querySelector("#latencyMs"),
  connectBtn: document.querySelector("#connectBtn"),
  recordBtn: document.querySelector("#recordBtn"),
  stopBtn: document.querySelector("#stopBtn"),
  status: document.querySelector("#status"),
  captionOverlay: document.querySelector("#captionOverlay"),
  captionLines: document.querySelector("#captionLines"),
  currentPartial: document.querySelector("#currentPartial"),
  finalLog: document.querySelector("#finalLog"),
  eventLog: document.querySelector("#eventLog"),
  spectrogram: document.querySelector("#spectrogram"),
  captionBg: document.querySelector("#captionBg"),
  captionOpacity: document.querySelector("#captionOpacity"),
  captionColor: document.querySelector("#captionColor"),
  unstableColor: document.querySelector("#unstableColor"),
  fontSize: document.querySelector("#fontSize"),
  lineCount: document.querySelector("#lineCount"),
  charsPerLine: document.querySelector("#charsPerLine"),
};

let ws = null;
let audioContext = null;
let mediaStream = null;
let sourceNode = null;
let processorNode = null;
let analyserNode = null;
let animationId = null;
let finalLines = [];
let partialLine = { stable: "", unstable: "" };

function logEvent(value) {
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  els.eventLog.textContent = `${text}\n${els.eventLog.textContent}`.slice(0, 6000);
}

function setStatus(text) {
  els.status.textContent = text;
}

function sendJson(payload) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify(payload));
}

function currentStartMessage() {
  return {
    type: "start",
    sample_rate: TARGET_SAMPLE_RATE,
    channels: 1,
    format: "pcm_s16le",
    language: els.language.value,
    task: "transcribe",
    latency_ms: Number(els.latencyMs.value),
    vad_mode: "server",
  };
}

function wrapText(text, charsPerLine) {
  const lines = [];
  for (let i = 0; i < text.length; i += charsPerLine) {
    lines.push(text.slice(i, i + charsPerLine));
  }
  return lines.length ? lines : [""];
}

function renderCaptions() {
  const lineCount = Number(els.lineCount.value);
  const charsPerLine = Number(els.charsPerLine.value);
  const stableLines = finalLines.flatMap((line) => wrapText(line, charsPerLine));
  const partialText = `${partialLine.stable}${partialLine.unstable}`;
  const partialWrapped = partialText ? wrapText(partialText, charsPerLine) : [];
  const combined = [...stableLines, ...partialWrapped].slice(-lineCount);

  els.captionLines.innerHTML = "";
  for (const line of combined) {
    const div = document.createElement("div");
    div.className = "caption-line";
    if (partialText && line === partialWrapped[partialWrapped.length - 1]) {
      const stableSpan = document.createElement("span");
      stableSpan.textContent = partialLine.stable;
      const unstableSpan = document.createElement("span");
      unstableSpan.className = "unstable";
      unstableSpan.textContent = partialLine.unstable;
      div.append(stableSpan, unstableSpan);
    } else {
      div.textContent = line;
    }
    els.captionLines.appendChild(div);
  }
}

function applyCaptionControls() {
  els.captionOverlay.style.background = hexToRgba(els.captionBg.value, Number(els.captionOpacity.value));
  els.captionOverlay.style.setProperty("--caption-color", els.captionColor.value);
  els.captionOverlay.style.setProperty("--caption-unstable", els.unstableColor.value);
  els.captionOverlay.style.setProperty("--caption-font-size", `${els.fontSize.value}px`);
  renderCaptions();
}

function hexToRgba(hex, alpha) {
  const normalized = hex.replace("#", "");
  const value = Number.parseInt(normalized, 16);
  const r = (value >> 16) & 255;
  const g = (value >> 8) & 255;
  const b = value & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function handleServerMessage(event) {
  const message = JSON.parse(event.data);
  logEvent(message);
  if (message.type === "ready") {
    sendJson(currentStartMessage());
  } else if (message.type === "config") {
    setStatus(`connected ${message.session_id || ""}`);
    els.recordBtn.disabled = false;
  } else if (message.type === "partial") {
    partialLine = {
      stable: message.stable_text || "",
      unstable: message.unstable_text || "",
    };
    els.currentPartial.innerHTML = `<span>${partialLine.stable}</span><span class="unstable">${partialLine.unstable}</span>`;
    renderCaptions();
  } else if (message.type === "final") {
    const text = message.text || `${message.stable_text || ""}${message.unstable_text || ""}`;
    if (text) {
      finalLines.push(text);
      finalLines = finalLines.slice(-20);
      const div = document.createElement("div");
      div.textContent = text;
      els.finalLog.appendChild(div);
    }
    partialLine = { stable: "", unstable: "" };
    els.currentPartial.textContent = "";
    renderCaptions();
  } else if (message.type === "stopped") {
    setStatus("stopped");
  } else if (message.type === "error") {
    setStatus("error");
  }
}

async function connect() {
  ws = new WebSocket(els.serverUrl.value);
  ws.binaryType = "arraybuffer";
  ws.addEventListener("open", () => {
    setStatus("socket open");
    els.connectBtn.disabled = true;
    els.stopBtn.disabled = false;
  });
  ws.addEventListener("message", handleServerMessage);
  ws.addEventListener("close", () => {
    setStatus("closed");
    els.connectBtn.disabled = false;
    els.recordBtn.disabled = true;
    els.stopBtn.disabled = true;
  });
  ws.addEventListener("error", () => setStatus("socket error"));
}

function downsampleToInt16(float32, inputSampleRate) {
  if (inputSampleRate === TARGET_SAMPLE_RATE) {
    return floatToInt16(float32);
  }
  const ratio = inputSampleRate / TARGET_SAMPLE_RATE;
  const outputLength = Math.floor(float32.length / ratio);
  const output = new Float32Array(outputLength);
  for (let i = 0; i < outputLength; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(Math.floor((i + 1) * ratio), float32.length);
    let sum = 0;
    for (let j = start; j < end; j += 1) sum += float32[j];
    output[i] = sum / Math.max(1, end - start);
  }
  return floatToInt16(output);
}

function floatToInt16(float32) {
  const int16 = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, float32[i]));
    int16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return int16;
}

const AUDACITY_COLORMAP = [
  [0.0, [0, 0, 0]],
  [0.08, [0, 7, 18]],
  [0.18, [0, 28, 61]],
  [0.34, [27, 28, 116]],
  [0.5, [108, 32, 157]],
  [0.66, [206, 31, 169]],
  [0.78, [255, 65, 92]],
  [0.9, [255, 155, 48]],
  [1.0, [255, 244, 176]],
];

function audacityColor(value) {
  const x = Math.max(0, Math.min(1, value / 255));
  for (let i = 1; i < AUDACITY_COLORMAP.length; i += 1) {
    const [rightStop, rightColor] = AUDACITY_COLORMAP[i];
    const [leftStop, leftColor] = AUDACITY_COLORMAP[i - 1];
    if (x <= rightStop) {
      const t = (x - leftStop) / Math.max(0.0001, rightStop - leftStop);
      const r = Math.round(leftColor[0] + (rightColor[0] - leftColor[0]) * t);
      const g = Math.round(leftColor[1] + (rightColor[1] - leftColor[1]) * t);
      const b = Math.round(leftColor[2] + (rightColor[2] - leftColor[2]) * t);
      return `rgb(${r}, ${g}, ${b})`;
    }
  }
  return "rgb(255, 244, 176)";
}

function drawSpectrogram() {
  if (!analyserNode) return;
  const canvas = els.spectrogram;
  const ctx = canvas.getContext("2d");
  const data = new Uint8Array(analyserNode.frequencyBinCount);
  analyserNode.getByteFrequencyData(data);
  const image = ctx.getImageData(1, 0, canvas.width - 1, canvas.height);
  ctx.putImageData(image, 0, 0);
  for (let y = 0; y < canvas.height; y += 1) {
    const index = Math.floor((1 - y / canvas.height) * data.length);
    const value = data[index] || 0;
    ctx.fillStyle = audacityColor(value);
    ctx.fillRect(canvas.width - 1, y, 1, 1);
  }
  animationId = requestAnimationFrame(drawSpectrogram);
}

async function startRecording() {
  mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  audioContext = new AudioContext();
  sourceNode = audioContext.createMediaStreamSource(mediaStream);
  analyserNode = audioContext.createAnalyser();
  analyserNode.fftSize = 1024;
  processorNode = audioContext.createScriptProcessor(4096, 1, 1);
  processorNode.onaudioprocess = (event) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const input = event.inputBuffer.getChannelData(0);
    const pcm = downsampleToInt16(input, audioContext.sampleRate);
    ws.send(pcm.buffer);
  };
  sourceNode.connect(analyserNode);
  sourceNode.connect(processorNode);
  processorNode.connect(audioContext.destination);
  setStatus("recording");
  els.recordBtn.disabled = true;
  drawSpectrogram();
}

function stopAll() {
  if (animationId) cancelAnimationFrame(animationId);
  if (processorNode) processorNode.disconnect();
  if (sourceNode) sourceNode.disconnect();
  if (mediaStream) mediaStream.getTracks().forEach((track) => track.stop());
  if (audioContext) audioContext.close();
  if (ws && ws.readyState === WebSocket.OPEN) sendJson({ type: "stop" });
  processorNode = null;
  sourceNode = null;
  mediaStream = null;
  audioContext = null;
  analyserNode = null;
  els.recordBtn.disabled = false;
}

els.connectBtn.addEventListener("click", connect);
els.recordBtn.addEventListener("click", startRecording);
els.stopBtn.addEventListener("click", stopAll);
els.language.addEventListener("change", () => {
  sendJson({ type: "config", language: els.language.value, language_apply: "next_utterance" });
});
els.latencyMs.addEventListener("change", () => {
  sendJson({ type: "config", latency_ms: Number(els.latencyMs.value) });
});
for (const input of [
  els.captionBg,
  els.captionOpacity,
  els.captionColor,
  els.unstableColor,
  els.fontSize,
  els.lineCount,
  els.charsPerLine,
]) {
  input.addEventListener("input", applyCaptionControls);
}
applyCaptionControls();
