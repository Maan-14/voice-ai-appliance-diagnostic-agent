/**
 * Real-time voice: stream LLM → sentence TTS queue → half-duplex mic.
 * End conversation hard-stops audio, queue, stream, and mic.
 */
import {
  createSession,
  persistSession,
  speakText,
  streamChat,
  transcribeBlob,
} from "./api.js";
import { AriaOrb } from "./orb.js";

const SPEECH_START = 0.045;
const SPEECH_HOLD = 0.028;
const SILENCE_MS = 900;
const MIN_SPEECH_MS = 450;
const MIN_CHUNK = 18;

const MAX_SOFT_CHUNK = 110;

/** Pull complete sentence chunks; leave remainder in the buffer. */
export function pullSentenceChunks(buffer) {
  const sentences = [];
  const re = /[.!?;]+(?=\s|$)/g;
  let lastCut = 0;
  const hits = [];
  let match;
  while ((match = re.exec(buffer)) !== null) {
    hits.push(match.index + match[0].length);
  }
  for (const end of hits) {
    const chunk = buffer.slice(lastCut, end).trim();
    if (chunk.length >= MIN_CHUNK || /[.!?]$/.test(chunk)) {
      sentences.push(chunk);
      lastCut = end;
    }
  }
  let rest = buffer.slice(lastCut);
  // Soft-flush long clauses without punctuation so TTS can start sooner.
  if (rest.trim().length >= MAX_SOFT_CHUNK) {
    const soft = rest.search(/,\s|\s(?:and|but|so|then)\s/i);
    if (soft > MIN_CHUNK) {
      const cut = soft + (rest[soft] === "," ? 1 : 0);
      const chunk = rest.slice(0, cut).trim();
      if (chunk) {
        sentences.push(chunk);
        rest = rest.slice(cut);
      }
    } else {
      const sp = rest.lastIndexOf(" ", MAX_SOFT_CHUNK);
      if (sp > MIN_CHUNK) {
        sentences.push(rest.slice(0, sp).trim());
        rest = rest.slice(sp);
      }
    }
  }
  return { sentences, rest };
}

export async function renderVoice(root, { go }) {
  const session = await createSession("voice");
  let conversationId = session.id || session.session_id;
  let callContext = session.call_context;
  let history = session.history || [];
  const startedAt = Date.now();

  /** @type {'idle'|'listening'|'thinking'|'speaking'|'ending'|'ended'} */
  let state = "idle";
  let running = false;
  let sessionEnded = false;
  let micMuted = true;
  let generationId = 0;
  let abortCtl = null;

  let audioCtx = null;
  let mediaStream = null;
  let analyser = null;
  let mediaRecorder = null;
  let recChunks = [];
  let userSpeaking = false;
  let speechStartedAt = 0;
  let lastLoudAt = 0;
  let rafMeter = 0;

  /** @type {{gen:number, text:string, blobPromise:Promise<Blob>}[]} */
  let ttsQueue = [];
  let queueRunning = false;
  let currentAudio = null;
  let audioUrl = null;
  let pulseTimer = null;
  let drainWaiters = [];

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

  let typedCaption = "";
  let typeGen = 0;
  let typeTimer = null;

  function sleep(ms) {
    return new Promise((r) => {
      typeTimer = setTimeout(r, ms);
    });
  }

  function stopTypewriter() {
    if (typeTimer) {
      clearTimeout(typeTimer);
      typeTimer = null;
    }
    typeGen += 1;
  }

  function resetCaption(placeholder) {
    stopTypewriter();
    typedCaption = "";
    caption.textContent = placeholder || "";
    caption.classList.toggle("muted", !placeholder || placeholder === "…" || placeholder.startsWith("Tell me"));
  }

  /**
   * Speak first, then type this chunk character-by-character (lags behind audio).
   * Not frame-synced — just speech-led caption.
   */
  async function typeChunkBehindSpeech(chunk, gen, durationSec) {
    if (!chunk || sessionEnded || gen !== generationId) return;
    const myType = ++typeGen;
    caption.classList.remove("muted");
    const sep = typedCaption && !/\s$/.test(typedCaption) ? " " : "";
    const target = typedCaption + sep + chunk;
    let pos = typedCaption.length + sep.length;

    // Let audio start first
    await sleep(140);
    if (sessionEnded || gen !== generationId || myType !== typeGen) return;

    const remaining = Math.max(1, target.length - pos);
    const budgetMs = Math.max(700, (durationSec || chunk.length * 0.055) * 1000 * 0.85);
    const step = Math.max(14, Math.min(42, budgetMs / remaining));

    while (pos < target.length) {
      if (sessionEnded || gen !== generationId || myType !== typeGen) return;
      pos += 1;
      caption.textContent = target.slice(0, pos);
      await sleep(step);
    }
    if (myType === typeGen && gen === generationId && !sessionEnded) {
      typedCaption = target;
      caption.textContent = target;
    }
  }

  function setUI(next, text) {
    if (sessionEnded && next !== "ended" && next !== "ending") return;
    state = next;
    orb.setState(
      next === "thinking"
        ? "thinking"
        : next === "speaking"
          ? "speaking"
          : next === "listening"
            ? "listening"
            : next === "ended"
              ? "ended"
              : "idle"
    );
    const labels = {
      idle: "Ready",
      listening: "Listening…",
      thinking: "Thinking…",
      speaking: "ARIA is speaking…",
      ending: "Ending…",
      ended: "Ended",
    };
    stateLabel.textContent = labels[next] || next;
    dot.className =
      next === "ended" || next === "ending"
        ? "dot off"
        : next === "thinking"
          ? "dot warn"
          : "dot live";
    // Only apply caption when explicitly passed — speaking captions come from typewriter
    if (text != null && next !== "speaking") {
      caption.textContent = text;
      caption.classList.toggle(
        "muted",
        next === "listening" || next === "idle" || !text
      );
    }
  }

  function bumpGeneration() {
    generationId += 1;
    return generationId;
  }

  function abortInFlight() {
    if (abortCtl) {
      try {
        abortCtl.abort();
      } catch {
        /* ignore */
      }
      abortCtl = null;
    }
  }

  function newSignal() {
    abortInFlight();
    abortCtl = new AbortController();
    return abortCtl.signal;
  }

  function hardStopAudio() {
    stopTypewriter();
    if (pulseTimer) {
      clearInterval(pulseTimer);
      pulseTimer = null;
    }
    if (currentAudio) {
      currentAudio.onended = null;
      currentAudio.onerror = null;
      try {
        currentAudio.pause();
        currentAudio.currentTime = 0;
        currentAudio.removeAttribute("src");
        currentAudio.load();
      } catch {
        /* ignore */
      }
      currentAudio = null;
    }
    if (audioUrl) {
      URL.revokeObjectURL(audioUrl);
      audioUrl = null;
    }
    orb.setLevel(0);
  }

  function clearTtsQueue() {
    ttsQueue = [];
    for (const w of drainWaiters) w();
    drainWaiters = [];
  }

  function waitForQueueDrain() {
    if (!queueRunning && ttsQueue.length === 0) return Promise.resolve();
    return new Promise((resolve) => {
      drainWaiters.push(resolve);
    });
  }

  function playBlob(blob, gen, text) {
    return new Promise((resolve) => {
      if (sessionEnded || gen !== generationId) {
        resolve();
        return;
      }
      if (pulseTimer) {
        clearInterval(pulseTimer);
        pulseTimer = null;
      }
      if (currentAudio) {
        currentAudio.onended = null;
        currentAudio.onerror = null;
        try {
          currentAudio.pause();
          currentAudio.removeAttribute("src");
          currentAudio.load();
        } catch {
          /* ignore */
        }
        currentAudio = null;
      }
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
        audioUrl = null;
      }

      audioUrl = URL.createObjectURL(blob);
      const audio = new Audio(audioUrl);
      currentAudio = audio;
      micMuted = true;
      setUI("speaking");

      let typingPromise = Promise.resolve();
      let startedTyping = false;
      const startTyping = () => {
        if (startedTyping || !text) return;
        startedTyping = true;
        const dur =
          Number.isFinite(audio.duration) && audio.duration > 0
            ? audio.duration
            : text.length * 0.055;
        typingPromise = typeChunkBehindSpeech(text, gen, dur);
      };

      let t = 0;
      pulseTimer = setInterval(() => {
        if (sessionEnded || gen !== generationId) {
          clearInterval(pulseTimer);
          pulseTimer = null;
          return;
        }
        t += 0.18;
        orb.setLevel(0.4 + Math.sin(t) * 0.3);
      }, 45);

      const finish = async () => {
        if (pulseTimer) clearInterval(pulseTimer);
        pulseTimer = null;
        if (audioUrl) URL.revokeObjectURL(audioUrl);
        audioUrl = null;
        currentAudio = null;
        orb.setLevel(0);
        try {
          await typingPromise;
        } catch {
          /* ignore */
        }
        // Ensure this chunk is fully visible before the next one
        if (text && gen === generationId && !sessionEnded) {
          const sep = typedCaption && !/\s$/.test(typedCaption) ? " " : "";
          if (!typedCaption.endsWith(text)) {
            typedCaption = typedCaption + sep + text;
          }
          caption.textContent = typedCaption;
          caption.classList.remove("muted");
        }
        resolve();
      };

      audio.addEventListener("loadedmetadata", startTyping, { once: true });
      audio.onended = () => {
        finish();
      };
      audio.onerror = () => {
        finish();
      };
      audio.play().then(startTyping).catch(() => finish());
    });
  }

  async function pumpQueue() {
    if (queueRunning) return;
    queueRunning = true;
    while (ttsQueue.length && !sessionEnded) {
      const item = ttsQueue.shift();
      if (!item || item.gen !== generationId) continue;
      try {
        const blob = await item.blobPromise;
        if (!blob || sessionEnded || item.gen !== generationId) continue;
        await playBlob(blob, item.gen, item.text);
      } catch {
        /* skip failed chunk */
      }
    }
    queueRunning = false;
    if (!ttsQueue.length) {
      for (const w of drainWaiters) w();
      drainWaiters = [];
    }
  }

  function enqueueSentence(text, gen) {
    const cleaned = (text || "").trim();
    if (!cleaned || sessionEnded || gen !== generationId) return;
    micMuted = true;
    if (state !== "speaking") setUI("speaking");
    const signal = abortCtl?.signal;
    const blobPromise = speakText(cleaned, signal).catch((err) => {
      if (err?.name === "AbortError") return null;
      throw err;
    });
    ttsQueue.push({ gen, text: cleaned, blobPromise });
    pumpQueue();
  }

  /** Speak known text with sentence chunking — caption types only after audio starts. */
  async function speakTextStreaming(fullText, gen) {
    if (sessionEnded || gen !== generationId) return;
    resetCaption("");
    setUI("speaking");
    let buf = "";
    const parts = fullText.match(/[^.!?;]+[.!?;]+|[^.!?;]+$/g) || [fullText];
    for (const part of parts) {
      if (sessionEnded || gen !== generationId) return;
      buf += part;
      const { sentences, rest } = pullSentenceChunks(buf);
      for (const s of sentences) enqueueSentence(s, gen);
      buf = rest;
    }
    if (buf.trim()) enqueueSentence(buf.trim(), gen);
    await waitForQueueDrain();
  }

  /** Stream agent turn → TTS ASAP; caption types behind speech only. */
  async function runStreamedAgentTurn(userText, gen) {
    if (sessionEnded || gen !== generationId) return;
    micMuted = true;
    resetCaption("…");
    setUI("thinking", "…");
    const signal = newSignal();
    let sentenceBuf = "";

    await streamChat({
      message: userText,
      callContext,
      history,
      conversationId,
      signal,
      onStatus() {
        if (!sessionEnded && gen === generationId && state !== "speaking") {
          setUI("thinking", "…");
        }
      },
      onDelta(delta) {
        if (sessionEnded || gen !== generationId) return;
        // Buffer for TTS only — do NOT dump assistant text into the caption yet
        sentenceBuf += delta;
        if (state !== "speaking") setUI("thinking", "…");
        const { sentences, rest } = pullSentenceChunks(sentenceBuf);
        sentenceBuf = rest;
        for (const s of sentences) enqueueSentence(s, gen);
      },
      onDone(payload) {
        if (sessionEnded || gen !== generationId) return;
        callContext = payload.call_context;
        history = payload.history || [];
        if (sentenceBuf.trim()) {
          enqueueSentence(sentenceBuf.trim(), gen);
          sentenceBuf = "";
        }
      },
    });

    await waitForQueueDrain();
  }

  function showEndedScreen() {
    setUI("ended", "");
    caption.textContent = "";
    caption.classList.add("muted");
    controls.innerHTML = `
      <div class="ended-panel">
        <h2>Conversation ended</h2>
        <p>Your conversation with ARIA has ended.</p>
        <button class="btn btn-primary" id="again" type="button">Start a new conversation →</button>
      </div>
    `;
    controls.querySelector("#again").onclick = () => go("voice");
  }

  async function stopAll({ persist = true } = {}) {
    sessionEnded = true;
    running = false;
    micMuted = true;
    userSpeaking = false;
    setUI("ending", caption.textContent || "");
    bumpGeneration();
    clearTtsQueue();
    hardStopAudio();
    abortInFlight();
    cancelAnimationFrame(rafMeter);
    rafMeter = 0;

    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      try {
        mediaRecorder.ondataavailable = null;
        mediaRecorder.onstop = null;
        mediaRecorder.stop();
      } catch {
        /* ignore */
      }
    }
    mediaRecorder = null;
    recChunks = [];

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
    analyser = null;

    if (persist) {
      const duration = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
      try {
        await persistSession(callContext, conversationId, duration);
      } catch {
        /* ignore */
      }
    }
    orb.stop();
    showEndedScreen();
  }

  function meterLoop() {
    if (!analyser || !running || sessionEnded) return;
    const data = new Uint8Array(analyser.frequencyBinCount);
    analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / data.length);
    const level = micMuted ? 0 : Math.min(1, rms * 4.5);
    if (!micMuted) orb.setLevel(level);

    if (!micMuted && state === "listening") {
      const now = performance.now();
      if (rms > SPEECH_START) {
        lastLoudAt = now;
        if (!userSpeaking) {
          userSpeaking = true;
          speechStartedAt = now;
          recChunks = [];
          if (mediaRecorder && mediaRecorder.state === "inactive") {
            try {
              mediaRecorder.start();
            } catch {
              /* ignore */
            }
          }
        }
      } else if (userSpeaking && rms < SPEECH_HOLD) {
        if (now - lastLoudAt > SILENCE_MS && now - speechStartedAt > MIN_SPEECH_MS) {
          userSpeaking = false;
          if (mediaRecorder && mediaRecorder.state === "recording") {
            try {
              mediaRecorder.stop();
            } catch {
              /* ignore */
            }
          }
        }
      }
    }
    rafMeter = requestAnimationFrame(meterLoop);
  }

  async function handleUtterance(blob) {
    const gen = generationId;
    if (sessionEnded || !running || gen !== generationId) return;
    if (blob.size < 800) {
      micMuted = false;
      resetCaption("Tell me what’s happening with your appliance.");
      setUI("listening", "Tell me what’s happening with your appliance.");
      return;
    }
    micMuted = true;
    resetCaption("…");
    setUI("thinking", "…");
    const signal = newSignal();
    try {
      const text = await transcribeBlob(blob, "utterance.webm", signal);
      if (sessionEnded || gen !== generationId) return;
      if (!text) {
        micMuted = false;
        resetCaption("I didn’t catch that — try again.");
        setUI("listening", "I didn’t catch that — try again.");
        return;
      }
      // Brief user caption while thinking — cleared before ARIA speaks
      caption.textContent = text;
      caption.classList.remove("muted");
      await runStreamedAgentTurn(text, gen);
      if (sessionEnded || gen !== generationId) return;
      micMuted = false;
      resetCaption("Tell me what’s happening with your appliance.");
      setUI("listening", "Tell me what’s happening with your appliance.");
    } catch (err) {
      if (err?.name === "AbortError" || sessionEnded) return;
      console.error(err);
      if (!sessionEnded) {
        micMuted = false;
        resetCaption("Something went wrong. I’m listening again.");
        setUI("listening", "Something went wrong. I’m listening again.");
      }
    }
  }

  root.querySelector("#back").onclick = async () => {
    await stopAll({ persist: true });
    go("landing");
  };

  startBtn.onclick = async () => {
    if (sessionEnded) return;
    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true },
      });
      if (sessionEnded) {
        mediaStream.getTracks().forEach((t) => t.stop());
        return;
      }
      audioCtx = new AudioContext();
      const source = audioCtx.createMediaStreamSource(mediaStream);
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);

      mediaRecorder = new MediaRecorder(mediaStream, {
        mimeType: MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "audio/webm",
      });
      mediaRecorder.ondataavailable = (e) => {
        if (sessionEnded || !e.data || e.data.size === 0) return;
        recChunks.push(e.data);
      };
      mediaRecorder.onstop = () => {
        if (sessionEnded || !running) return;
        const blob = new Blob(recChunks, {
          type: mediaRecorder?.mimeType || "audio/webm",
        });
        recChunks = [];
        handleUtterance(blob);
      };

      running = true;
      sessionEnded = false;
      const gen = bumpGeneration();
      startBtn.hidden = true;
      endBtn.hidden = false;
      orb.start();
      micMuted = true;
      setUI("thinking");
      resetCaption("");

      // Audio first; caption types character-by-character after speech starts
      await speakTextStreaming(session.greeting, gen);
      if (sessionEnded || gen !== generationId) return;

      micMuted = false;
      resetCaption("Tell me what’s happening with your appliance.");
      setUI("listening", "Tell me what’s happening with your appliance.");
      meterLoop();
    } catch (err) {
      console.error(err);
      setUI("idle", "Microphone permission is required for voice mode.");
    }
  };

  endBtn.onclick = () => {
    // Sync hard-stop first — kill audio before any await
    sessionEnded = true;
    running = false;
    micMuted = true;
    bumpGeneration();
    clearTtsQueue();
    hardStopAudio();
    abortInFlight();
    stopAll({ persist: true });
  };
}
