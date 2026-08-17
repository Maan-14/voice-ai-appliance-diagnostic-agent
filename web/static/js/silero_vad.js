/**
 * Load Silero VAD (@ricky0123/vad-web) from CDN for a no-bundler SPA.
 * Falls back to null if CDN/WASM fails — callers should use energy VAD.
 */
const ORT_SRC =
  "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0/dist/ort.wasm.min.js";
const VAD_SRC =
  "https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.29/dist/bundle.min.js";
const ORT_WASM =
  "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.22.0/dist/";
const VAD_ASSETS =
  "https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.29/dist/";

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-aria-src="${src}"]`);
    if (existing) {
      if (existing.dataset.loaded === "1") resolve();
      else existing.addEventListener("load", () => resolve(), { once: true });
      return;
    }
    const s = document.createElement("script");
    s.src = src;
    s.async = true;
    s.dataset.ariaSrc = src;
    s.onload = () => {
      s.dataset.loaded = "1";
      resolve();
    };
    s.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(s);
  });
}

/**
 * @param {object} opts
 * @param {() => Promise<MediaStream>} opts.getStream
 * @param {() => void} [opts.onSpeechStart]
 * @param {() => void} [opts.onSpeechEnd]
 * @param {() => void} [opts.onVADMisfire]
 * @param {(probs: {isSpeech: number}) => void} [opts.onFrameProcessed]
 * @param {number} [opts.positiveSpeechThreshold]
 * @param {number} [opts.negativeSpeechThreshold]
 * @param {number} [opts.minSpeechFrames]
 */
export async function createSileroVad(opts) {
  await loadScript(ORT_SRC);
  await loadScript(VAD_SRC);
  const MicVAD = window.vad?.MicVAD;
  if (!MicVAD) throw new Error("MicVAD not available on window.vad");

  const instance = await MicVAD.new({
    getStream: opts.getStream,
    pauseStream: async () => {},
    resumeStream: async (stream) => stream,
    onnxWASMBasePath: ORT_WASM,
    baseAssetPath: VAD_ASSETS,
    positiveSpeechThreshold: opts.positiveSpeechThreshold ?? 0.55,
    negativeSpeechThreshold: opts.negativeSpeechThreshold ?? 0.35,
    minSpeechFrames: opts.minSpeechFrames ?? 6,
    redemptionFrames: opts.redemptionFrames ?? 12,
    preSpeechPadFrames: opts.preSpeechPadFrames ?? 3,
    onSpeechStart: () => opts.onSpeechStart?.(),
    onSpeechEnd: () => opts.onSpeechEnd?.(),
    onVADMisfire: () => opts.onVADMisfire?.(),
    onFrameProcessed: (probs) => opts.onFrameProcessed?.(probs),
  });

  return instance;
}
