/**
 * Browser Talk-to-ARIA — automatic speech ↔ OpenAI Realtime ↔ speech.
 * Silero VAD (same idea as pre-Realtime voice) gates the mic so room noise
 * is not streamed; only near speech is sent. No push-to-talk.
 */
import { createSession, persistSession } from "./api.js";
import { AriaOrb } from "./orb.js";
import { createSileroVad } from "./silero_vad.js";

const TARGET_RATE = 24000;
const FRAME_SAMPLES = 2400; // 100ms @ 24 kHz
/** Accumulate ~80ms before scheduling to reduce crackle from tiny deltas. */
const PLAY_MIN_SAMPLES = 1920;
const VAD_POS = 0.58;
const VAD_NEG = 0.35;
const VAD_MIN_FRAMES = 5;
const ENERGY_OPEN = 0.03;
const ENERGY_HOLD = 0.018;
const ENERGY_BARGE = 0.06;
const ENERGY_OPEN_FRAMES = 3;
const ENERGY_HANG_MS = 500;

function floatTo16BitPCM(float32) {
  const out = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

function downsampleTo24k(float32, inputRate) {
  if (inputRate === TARGET_RATE) return floatTo16BitPCM(float32);
  const ratio = inputRate / TARGET_RATE;
  const newLen = Math.max(1, Math.floor(float32.length / ratio));
  const down = new Float32Array(newLen);
  for (let i = 0; i < newLen; i++) {
    down[i] = float32[Math.floor(i * ratio)] || 0;
  }
  return floatTo16BitPCM(down);
}

function pcm16ToBase64(int16) {
  const bytes = new Uint8Array(int16.buffer, int16.byteOffset, int16.byteLength);
  let binary = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
  }
  return btoa(binary);
}

function base64ToInt16(b64) {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new Int16Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 2);
}

function rmsInt16(int16) {
  if (!int16.length) return 0;
  let sum = 0;
  for (let i = 0; i < int16.length; i++) {
    const v = int16[i] / 32768;
    sum += v * v;
  }
  return Math.sqrt(sum / int16.length);
}

async function openMicStream() {
  const ideal = {
    channelCount: { ideal: 1 },
    echoCancellation: { ideal: true },
    noiseSuppression: { ideal: true },
    autoGainControl: { ideal: true },
    voiceIsolation: { ideal: true },
  };
  try {
    return await navigator.mediaDevices.getUserMedia({ audio: ideal });
  } catch {
    return navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
  }
}

export async function renderVoice(root, { go }) {
  const session = await createSession("voice");
  let conversationId = session.id || session.session_id;
  let callContext = session.call_context;
  const startedAt = Date.now();

  let state = "idle";
  let running = false;
  let sessionEnded = false;
  let ws = null;
  let mediaStream = null;
  let audioCtx = null;
  let processor = null;
  let micSource = null;
  let playGain = null;
  /** @type {AudioBufferSourceNode[]} */
  let activeSources = [];
  let nextPlayTime = 0;
  let playPcmPending = new Int16Array(0);
  let pendingMic = new Int16Array(0);
  let agentPlaying = false;
  let silero = null;
  let useSilero = false;
  /** True while local VAD says the near user is speaking. */
  let userSpeaking = false;
  let energyLoudFrames = 0;
  let energyHangUntil = 0;
  let agentDoneTimer = null;

  root.innerHTML = `
    <div class="voice-shell">
      <header class="topbar">
        <button class="back" id="back" type="button">
          ← ARIA
          <small>Appliance Diagnostic Agent</small>
        </button>
      </header>
      <div class="voice-stage" id="stage">
        <div class="voice-title">ARIA</div>
        <div class="voice-sub">Appliance Diagnostic Agent</div>
        <div class="orb-wrap"><canvas id="orb"></canvas></div>
        <div class="voice-state"><span class="dot live" id="dot"></span><span id="stateLabel">Ready</span></div>
        <div class="voice-caption muted" id="caption">Start a voice conversation to begin.</div>
        <p class="voice-hint">Speak near the mic. Headphones are recommended.</p>
        <div class="voice-controls" id="controls">
          <button class="btn btn-primary" id="start" type="button">Start voice conversation</button>
          <button class="btn btn-danger" id="end" type="button" hidden>End conversation</button>
        </div>
      </div>
    </div>
  `;

  const orb = new AriaOrb(root.querySelector("#orb"));
  orb.start();
  const caption = root.querySelector("#caption");
  const stateLabel = root.querySelector("#stateLabel");
  const dot = root.querySelector("#dot");
  const startBtn = root.querySelector("#start");
  const endBtn = root.querySelector("#end");
  const controls = root.querySelector("#controls");

  function setState(next, text) {
    state = next;
    const orbState =
      next === "speaking"
        ? "speaking"
        : next === "listening" || next === "user_speaking"
          ? next === "user_speaking"
            ? "user_speaking"
            : "listening"
          : next === "thinking"
            ? "thinking"
            : next === "ended"
              ? "ended"
              : "idle";
    orb.setState(orbState);
    const labels = {
      idle: "Ready",
      connecting: "Connecting…",
      listening: "Listening…",
      user_speaking: "Listening…",
      thinking: "Thinking…",
      speaking: "ARIA is speaking…",
      ending: "Ending…",
      ended: "Ended",
    };
    stateLabel.textContent = labels[next] || next;
    dot.className =
      next === "ended" || next === "ending"
        ? "dot off"
        : next === "thinking" || next === "connecting"
          ? "dot warn"
          : "dot live";
    if (text != null) {
      caption.textContent = text;
      caption.classList.toggle(
        "muted",
        !text || next === "listening" || next === "idle" || next === "connecting"
      );
    }
  }

  function clearPlayback() {
    if (agentDoneTimer) {
      clearTimeout(agentDoneTimer);
      agentDoneTimer = null;
    }
    playPcmPending = new Int16Array(0);
    agentPlaying = false;
    nextPlayTime = 0;
    for (const source of activeSources) {
      try {
        source.onended = null;
        source.stop(0);
      } catch {
        /* ignore */
      }
      try {
        source.disconnect();
      } catch {
        /* ignore */
      }
    }
    activeSources = [];
    orb.setLevel(0);
  }

  function flushPlayPending(force = false) {
    if (!audioCtx || sessionEnded) {
      playPcmPending = new Int16Array(0);
      return;
    }
    while (playPcmPending.length > 0) {
      if (!force && playPcmPending.length < PLAY_MIN_SAMPLES) break;
      const take = force
        ? playPcmPending.length
        : Math.min(playPcmPending.length, PLAY_MIN_SAMPLES * 2);
      const chunk = playPcmPending.slice(0, take);
      playPcmPending = playPcmPending.slice(take);
      scheduleGapless(chunk);
      if (force) break;
    }
  }

  function enqueuePcm(int16) {
    if (!int16.length || sessionEnded || !audioCtx) return;
    agentPlaying = true;
    const merged = new Int16Array(playPcmPending.length + int16.length);
    merged.set(playPcmPending);
    merged.set(int16, playPcmPending.length);
    playPcmPending = merged;
    flushPlayPending(false);
  }

  function scheduleGapless(int16) {
    if (!audioCtx || !int16.length) return;
    const floats = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) floats[i] = int16[i] / 32768;
    const buffer = audioCtx.createBuffer(1, floats.length, TARGET_RATE);
    buffer.copyToChannel(floats, 0);
    const source = audioCtx.createBufferSource();
    source.buffer = buffer;
    source.connect(playGain || audioCtx.destination);
    const now = audioCtx.currentTime;
    // Small lead-in; then stitch buffers with no gap (fixes shatter/crackle).
    if (nextPlayTime < now + 0.04) nextPlayTime = now + 0.04;
    const startAt = nextPlayTime;
    nextPlayTime = startAt + buffer.duration;
    activeSources.push(source);
    orb.setLevel(Math.min(1, 0.35 + rmsInt16(int16) * 4));
    source.onended = () => {
      activeSources = activeSources.filter((s) => s !== source);
      try {
        source.disconnect();
      } catch {
        /* ignore */
      }
      if (!activeSources.length && !playPcmPending.length) {
        agentPlaying = false;
        orb.setLevel(0);
        if (!sessionEnded && running && (state === "speaking" || state === "thinking")) {
          setState("listening", caption.textContent || "Listening…");
        }
      }
    };
    try {
      source.start(startAt);
    } catch {
      activeSources = activeSources.filter((s) => s !== source);
    }
  }

  function wsUrl() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${location.host}/api/aria/ws/realtime`;
  }

  function onLocalSpeechStart() {
    if (sessionEnded || !running) return;
    userSpeaking = true;
    if (agentPlaying || state === "speaking") {
      clearPlayback();
      try {
        ws?.send(JSON.stringify({ type: "cancel" }));
      } catch {
        /* ignore */
      }
    }
    if (state !== "thinking") {
      setState("user_speaking", "Listening…");
    }
  }

  function onLocalSpeechEnd() {
    userSpeaking = false;
    energyLoudFrames = 0;
    if (!sessionEnded && running && state === "user_speaking") {
      setState("thinking", "…");
    }
  }

  function energyAllowsSend(rms) {
    const now = performance.now();
    const openTh = agentPlaying || state === "speaking" ? ENERGY_BARGE : ENERGY_OPEN;
    if (rms >= openTh) {
      energyLoudFrames += 1;
      if (energyLoudFrames >= ENERGY_OPEN_FRAMES) {
        energyHangUntil = now + ENERGY_HANG_MS;
        return true;
      }
      return energyHangUntil > now;
    }
    energyLoudFrames = Math.max(0, energyLoudFrames - 1);
    return energyHangUntil > now && rms >= ENERGY_HOLD;
  }

  /** Only stream when local VAD says this is real near speech (old-path behavior). */
  function shouldStreamMic(rms) {
    if (useSilero) return userSpeaking;
    return energyAllowsSend(rms);
  }

  function handleServerMessage(msg) {
    const type = msg.type;
    if (type === "ready") {
      setState("listening", "Connected. Talk when you are ready.");
      return;
    }
    if (type === "audio" && msg.audio) {
      setState("speaking");
      enqueuePcm(base64ToInt16(msg.audio));
      return;
    }
    if (type === "agent_speaking") {
      setState("speaking");
      return;
    }
    if (type === "agent_done") {
      // Flush remaining PCM and let scheduled audio finish cleanly.
      flushPlayPending(true);
      return;
    }
    if (type === "user_speech_started") {
      onLocalSpeechStart();
      return;
    }
    if (type === "user_speech_stopped") {
      if (!useSilero) onLocalSpeechEnd();
      return;
    }
    if (type === "error") {
      console.error("Realtime error", msg.message);
      if (!sessionEnded) {
        setState(state === "idle" ? "idle" : "listening", msg.message || "Voice error");
      }
    }
  }

  function startMicPump() {
    if (!audioCtx || !mediaStream) return;
    micSource = audioCtx.createMediaStreamSource(mediaStream);
    processor = audioCtx.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (ev) => {
      if (sessionEnded || !running || !ws || ws.readyState !== WebSocket.OPEN) return;
      const input = ev.inputBuffer.getChannelData(0);
      const pcm = downsampleTo24k(input, audioCtx.sampleRate);
      const rms = rmsInt16(pcm);
      if (state === "listening" || state === "user_speaking") {
        orb.setLevel(Math.min(1, rms * 5));
      }

      if (!shouldStreamMic(rms)) return;

      if (!useSilero && !userSpeaking && energyLoudFrames >= ENERGY_OPEN_FRAMES) {
        onLocalSpeechStart();
      }

      const merged = new Int16Array(pendingMic.length + pcm.length);
      merged.set(pendingMic);
      merged.set(pcm, pendingMic.length);
      pendingMic = merged;
      while (pendingMic.length >= FRAME_SAMPLES) {
        const frame = pendingMic.slice(0, FRAME_SAMPLES);
        pendingMic = pendingMic.slice(FRAME_SAMPLES);
        try {
          ws.send(JSON.stringify({ type: "audio", audio: pcm16ToBase64(frame) }));
        } catch {
          /* ignore */
        }
      }
    };
    micSource.connect(processor);
    const silent = audioCtx.createGain();
    silent.gain.value = 0;
    processor.connect(silent);
    silent.connect(audioCtx.destination);
  }

  async function startVad() {
    try {
      silero = await createSileroVad({
        getStream: async () => mediaStream,
        positiveSpeechThreshold: VAD_POS,
        negativeSpeechThreshold: VAD_NEG,
        minSpeechFrames: VAD_MIN_FRAMES,
        redemptionFrames: 14,
        onSpeechStart: onLocalSpeechStart,
        onSpeechEnd: onLocalSpeechEnd,
        onVADMisfire: () => {
          userSpeaking = false;
        },
      });
      await silero.start();
      useSilero = true;
    } catch (err) {
      console.warn("Silero VAD unavailable, using energy gate", err);
      useSilero = false;
      silero = null;
    }
  }

  async function destroyVad() {
    if (silero) {
      try {
        silero.pause?.();
      } catch {
        /* ignore */
      }
      try {
        await silero.destroy?.();
      } catch {
        /* ignore */
      }
    }
    silero = null;
    useSilero = false;
    userSpeaking = false;
  }

  async function stopAll({ persist = true } = {}) {
    if (sessionEnded && state === "ended") return;
    sessionEnded = true;
    running = false;
    setState("ending", caption.textContent || "");
    clearPlayback();
    pendingMic = new Int16Array(0);
    await destroyVad();

    try {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "end" }));
      }
    } catch {
      /* ignore */
    }
    try {
      ws?.close();
    } catch {
      /* ignore */
    }
    ws = null;

    try {
      processor?.disconnect();
    } catch {
      /* ignore */
    }
    try {
      micSource?.disconnect();
    } catch {
      /* ignore */
    }
    processor = null;
    micSource = null;

    if (mediaStream) {
      mediaStream.getTracks().forEach((t) => t.stop());
      mediaStream = null;
    }
    if (audioCtx) {
      try {
        await audioCtx.close();
      } catch {
        /* ignore */
      }
      audioCtx = null;
    }

    const duration = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
    if (persist) {
      try {
        await persistSession(callContext, conversationId, duration);
      } catch {
        /* ignore */
      }
    }
    orb.stop();
    await showEndedScreen(duration);
  }

  async function showEndedScreen(durationSeconds) {
    setState("ended");
    caption.textContent = "";
    caption.classList.add("muted");
    controls.innerHTML = `
      <div class="ended-panel">
        <h2>Conversation ended</h2>
        <p>Your conversation with ARIA has ended${
          durationSeconds ? ` (${durationSeconds}s)` : ""
        }.</p>
        <div class="ended-actions">
          <button class="btn btn-primary" id="again" type="button">Start a new conversation →</button>
        </div>
      </div>
    `;
    controls.querySelector("#again").onclick = () => go("voice");
  }

  root.querySelector("#back").onclick = async () => {
    await stopAll({ persist: true });
    go("landing");
  };

  startBtn.onclick = async () => {
    if (sessionEnded || running) return;
    try {
      setState("connecting", "Allow microphone access…");
      mediaStream = await openMicStream();
      // Prefer 24 kHz so playback matches Realtime PCM without resampling artifacts.
      try {
        audioCtx = new AudioContext({ sampleRate: TARGET_RATE });
      } catch {
        audioCtx = new AudioContext();
      }
      if (audioCtx.state === "suspended") await audioCtx.resume();
      playGain = audioCtx.createGain();
      playGain.gain.value = 1;
      playGain.connect(audioCtx.destination);
      nextPlayTime = 0;

      ws = new WebSocket(wsUrl());
      await new Promise((resolve, reject) => {
        const t = setTimeout(() => reject(new Error("WebSocket timeout")), 15000);
        ws.onopen = () => {
          clearTimeout(t);
          resolve();
        };
        ws.onerror = () => {
          clearTimeout(t);
          reject(new Error("WebSocket failed"));
        };
      });

      ws.onmessage = (ev) => {
        try {
          handleServerMessage(JSON.parse(ev.data));
        } catch (err) {
          console.error(err);
        }
      };
      ws.onclose = () => {
        if (!sessionEnded && running) stopAll({ persist: true });
      };

      ws.send(
        JSON.stringify({
          type: "start",
          conversation_id: conversationId,
          call_context: callContext,
        })
      );

      running = true;
      startBtn.hidden = true;
      endBtn.hidden = false;
      await startVad();
      startMicPump();
      setState("listening", "Talk when you are ready.");
    } catch (err) {
      console.error(err);
      setState("idle", "Microphone permission and a live server are required for voice mode.");
      if (mediaStream) {
        mediaStream.getTracks().forEach((t) => t.stop());
        mediaStream = null;
      }
    }
  };

  endBtn.onclick = () => stopAll({ persist: true });
}
