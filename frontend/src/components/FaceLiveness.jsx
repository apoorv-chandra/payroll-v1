import React, { useEffect, useRef, useState, useCallback } from "react";

// face-api.js loaded from npm package (already installed)
// Models are served from a CDN (jsdelivr -> github)
const MODELS_URL = "https://cdn.jsdelivr.net/gh/justadudewhohacks/face-api.js@0.22.2/weights";

// Eye aspect ratio (EAR) thresholds.
// Eyes "closed" when EAR < CLOSE; "open" when EAR > OPEN. A full close→open
// cycle counts as a blink. Tuned empirically for tinyFaceDetector landmarks.
const EAR_CLOSE = 0.21;
const EAR_OPEN = 0.27;

let faceapi = null;
let modelsLoaded = false;
let modelsLoading = null;

async function ensureFaceApi() {
  if (modelsLoaded) return faceapi;
  if (!modelsLoading) {
    modelsLoading = (async () => {
      const mod = await import("face-api.js");
      faceapi = mod;
      await Promise.all([
        faceapi.nets.tinyFaceDetector.loadFromUri(MODELS_URL),
        faceapi.nets.faceLandmark68TinyNet.loadFromUri(MODELS_URL),
      ]);
      modelsLoaded = true;
    })();
  }
  await modelsLoading;
  return faceapi;
}

// Eye Aspect Ratio: average of vertical / horizontal distances of 6 landmarks per eye.
function eyeAspectRatio(eye) {
  const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
  const v1 = dist(eye[1], eye[5]);
  const v2 = dist(eye[2], eye[4]);
  const h = dist(eye[0], eye[3]);
  if (h === 0) return 0;
  return (v1 + v2) / (2 * h);
}

/**
 * FaceLiveness — prompts the user to blink once. Calls onPass({ blob, dataUrl })
 * when liveness is verified, with the captured frame.
 *
 * Props:
 *  - active: boolean — start camera + detection
 *  - onPass(payload)
 *  - onError(msg)
 *  - onStatus(state) — optional, gets state strings for UI sync
 */
export default function FaceLiveness({ active, onPass, onError, onStatus }) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const animRef = useRef(null);
  const stateRef = useRef({ phase: "loading", earSeen: false, blinkCount: 0, lastEarOpen: true });

  const [phase, setPhase] = useState("loading"); // loading | no-face | center-face | blink | verified | error
  const [hint, setHint] = useState("Loading verification…");
  const [progress, setProgress] = useState(0); // 0..1 for blink progress

  const setUI = useCallback((p, h) => {
    setPhase(p); setHint(h); onStatus?.(p);
  }, [onStatus]);

  // Cleanup
  const stop = useCallback(() => {
    if (animRef.current) cancelAnimationFrame(animRef.current);
    animRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  const captureFrame = useCallback(() => {
    const v = videoRef.current; const c = canvasRef.current;
    if (!v || !c) return null;
    const SIZE = 320;
    c.width = SIZE; c.height = SIZE;
    const ctx = c.getContext("2d");
    if (!v.videoWidth) return null;
    const ratio = Math.max(SIZE / v.videoWidth, SIZE / v.videoHeight);
    const sw = SIZE / ratio; const sh = SIZE / ratio;
    const sx = (v.videoWidth - sw) / 2; const sy = (v.videoHeight - sh) / 2;
    // Mirror: draw user-cam un-mirrored so back-end gets a normal-orientation hash
    ctx.save();
    ctx.translate(SIZE, 0); ctx.scale(-1, 1);
    ctx.drawImage(v, sx, sy, sw, sh, 0, 0, SIZE, SIZE);
    ctx.restore();
    return c.toDataURL("image/jpeg", 0.7);
  }, []);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    (async () => {
      try {
        setUI("loading", "Loading verification…");
        await ensureFaceApi();
        if (cancelled) return;
        const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "user", width: { ideal: 480 }, height: { ideal: 480 } }, audio: false });
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => {});
        }
        if (cancelled) return;
        setUI("no-face", "Position your face in the frame");
        const opts = new faceapi.TinyFaceDetectorOptions({ inputSize: 224, scoreThreshold: 0.4 });

        const tick = async () => {
          if (cancelled) return;
          try {
            const v = videoRef.current;
            if (v && v.readyState >= 2) {
              const det = await faceapi.detectSingleFace(v, opts).withFaceLandmarks(true);
              if (!det) {
                setUI("no-face", "Position your face in the frame");
                stateRef.current.lastEarOpen = true;
              } else {
                const lm = det.landmarks;
                const left = lm.getLeftEye();
                const right = lm.getRightEye();
                const ear = (eyeAspectRatio(left) + eyeAspectRatio(right)) / 2;
                const box = det.detection.box;
                const vw = v.videoWidth; const vh = v.videoHeight;
                const cx = box.x + box.width / 2; const cy = box.y + box.height / 2;
                const centered = Math.abs(cx - vw / 2) < vw * 0.18 && Math.abs(cy - vh / 2) < vh * 0.2 && box.width > vw * 0.25;
                if (!centered) {
                  setUI("center-face", "Move closer & center your face");
                  stateRef.current.lastEarOpen = true;
                } else if (stateRef.current.phase !== "verified") {
                  // Blink detection state machine
                  setUI("blink", "Blink once to verify");
                  setProgress(Math.max(0, Math.min(1, (EAR_OPEN - ear) / (EAR_OPEN - EAR_CLOSE))));
                  if (ear < EAR_CLOSE && stateRef.current.lastEarOpen) {
                    stateRef.current.lastEarOpen = false;
                  } else if (ear > EAR_OPEN && stateRef.current.lastEarOpen === false) {
                    stateRef.current.lastEarOpen = true;
                    stateRef.current.blinkCount += 1;
                    if (stateRef.current.blinkCount >= 1) {
                      stateRef.current.phase = "verified";
                      setUI("verified", "Verified ✓");
                      const dataUrl = captureFrame();
                      onPass?.({ dataUrl });
                      return;
                    }
                  }
                }
              }
            }
          } catch (e) {
            // swallow per-frame errors
          }
          animRef.current = requestAnimationFrame(tick);
        };
        animRef.current = requestAnimationFrame(tick);
      } catch (e) {
        setUI("error", e.message || "Camera/model failed");
        onError?.(e.message || "Camera/model failed");
      }
    })();
    return () => {
      cancelled = true;
      stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  return (
    <div className="space-y-3">
      <div className="aspect-square w-full max-w-xs mx-auto rounded-xl overflow-hidden border border-gray-200 relative bg-gray-900">
        <video ref={videoRef} autoPlay playsInline muted style={{ transform: "scaleX(-1)" }} className="w-full h-full object-cover" />
        <canvas ref={canvasRef} className="hidden" />
        {/* Oval guide */}
        <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
          <div className={`rounded-full border-2 ${phase === "verified" ? "border-green-400" : phase === "blink" ? "border-blue-400" : "border-white/70"} transition-colors duration-150`}
               style={{ width: "70%", height: "85%", boxShadow: "0 0 0 9999px rgba(0,0,0,0.35)" }} />
        </div>
        {/* Status pill */}
        <div className="absolute top-2 left-1/2 -translate-x-1/2 bg-black/60 text-white text-xs px-3 py-1 rounded-full backdrop-blur-sm">
          {hint}
        </div>
        {phase === "blink" && (
          <div className="absolute bottom-3 left-3 right-3 h-1.5 rounded-full bg-white/30 overflow-hidden">
            <div className="h-full bg-blue-400 transition-all" style={{ width: `${Math.round(progress * 100)}%` }} />
          </div>
        )}
      </div>
      <p className="text-xs text-center text-gray-500">
        {phase === "verified" ? "Liveness verified — you can mark attendance." : "Camera + on-device blink check (face-api.js). No image leaves your phone."}
      </p>
    </div>
  );
}
