/**
 * MediaPipe Hand Landmarker wrapper (lazy, degradable).
 *
 * The wasm runtime ships from our own origin via bundled assets. The
 * landmark model is fetched from /models/hand_landmarker.task when the
 * operator has installed it locally, falling back to the MediaPipe CDN in
 * development. When neither is available (production CSP forbids external
 * fetches), HoloConsole reports "unavailable" and the interface keeps full
 * keyboard/mouse parity — a designed degraded state, not an error.
 */

import type { RawHand } from "./landmarks";

const LOCAL_MODEL_URL = "/models/hand_landmarker.task";
const CDN_MODEL_URL =
  "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";

export type HandTracker = {
  detect: (video: HTMLVideoElement, timestampMs: number) => RawHand[];
  close: () => void;
};

export type TrackerOutcome =
  | { status: "ready"; tracker: HandTracker }
  | { status: "unavailable"; reason: string };

async function resolveModelUrl(): Promise<string | null> {
  try {
    const local = await fetch(LOCAL_MODEL_URL, { method: "HEAD" });
    if (local.ok) {
      return LOCAL_MODEL_URL;
    }
  } catch {
    // Fall through to the CDN probe.
  }
  if (import.meta.env.DEV) {
    return CDN_MODEL_URL;
  }
  return null;
}

export async function createHandTracker(): Promise<TrackerOutcome> {
  let modelUrl: string | null;
  try {
    modelUrl = await resolveModelUrl();
  } catch {
    modelUrl = null;
  }
  if (modelUrl === null) {
    return {
      status: "unavailable",
      reason:
        "The hand model is not installed locally; gesture control is off. Keyboard and mouse controls remain fully available.",
    };
  }
  try {
    const vision = await import("@mediapipe/tasks-vision");
    const wasmLoader = (
      await import(
        "@mediapipe/tasks-vision/wasm/vision_wasm_internal.js?url"
      )
    ).default;
    const wasmBinary = (
      await import(
        "@mediapipe/tasks-vision/wasm/vision_wasm_internal.wasm?url"
      )
    ).default;
    const landmarker = await vision.HandLandmarker.createFromOptions(
      {
        wasmLoaderPath: wasmLoader,
        wasmBinaryPath: wasmBinary,
      },
      {
        baseOptions: { modelAssetPath: modelUrl, delegate: "GPU" },
        runningMode: "VIDEO",
        numHands: 2,
        minHandDetectionConfidence: 0.5,
        minHandPresenceConfidence: 0.5,
        minTrackingConfidence: 0.5,
      },
    );
    return {
      status: "ready",
      tracker: {
        detect(video, timestampMs) {
          const result = landmarker.detectForVideo(video, timestampMs);
          const hands: RawHand[] = [];
          result.landmarks.forEach((landmarks, index) => {
            const categories = result.handedness[index];
            const category = categories?.[0];
            if (category === undefined) {
              return;
            }
            hands.push({
              landmarks: landmarks.map((point) => ({
                // Mirror horizontally: the operator faces the camera.
                x: 1 - point.x,
                y: point.y,
              })),
              handedness:
                category.categoryName === "Left" ? "Left" : "Right",
              score: category.score,
            });
          });
          return hands;
        },
        close() {
          landmarker.close();
        },
      },
    };
  } catch {
    return {
      status: "unavailable",
      reason:
        "The gesture runtime could not start in this browser. Keyboard and mouse controls remain fully available.",
    };
  }
}
