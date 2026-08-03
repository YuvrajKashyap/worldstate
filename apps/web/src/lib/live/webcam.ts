/**
 * Webcam lifecycle (CAP-001, CAP-002): frames are captured only after
 * explicit user action, and every media track is stopped on release.
 */

export type WebcamHandle = {
  stream: MediaStream;
  video: HTMLVideoElement;
  release: () => void;
};

export type WebcamFailure =
  | "denied"
  | "no-device"
  | "in-use"
  | "insecure-context"
  | "timeout"
  | "no-frame"
  | "unknown";

const CAMERA_PERMISSION_TIMEOUT_MS = 20_000;
const CAMERA_FRAME_TIMEOUT_MS = 5_000;

export type AcquireWebcamOptions = {
  permissionTimeoutMs?: number;
  frameTimeoutMs?: number;
  createVideo?: () => HTMLVideoElement;
};

export class WebcamError extends Error {
  readonly reason: WebcamFailure;

  constructor(reason: WebcamFailure, message: string) {
    super(message);
    this.name = "WebcamError";
    this.reason = reason;
  }
}

function hasUsableFrame(video: HTMLVideoElement): boolean {
  return (
    video.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA &&
    video.videoWidth > 0 &&
    video.videoHeight > 0
  );
}

async function waitForFirstFrame(
  video: HTMLVideoElement,
  timeoutMs: number,
): Promise<void> {
  if (hasUsableFrame(video)) {
    return;
  }
  await new Promise<void>((resolve, reject) => {
    const events = ["loadeddata", "canplay", "playing", "resize"] as const;
    let timeoutId = 0;
    const cleanup = () => {
      window.clearTimeout(timeoutId);
      for (const event of events) {
        video.removeEventListener(event, check);
      }
    };
    const check = () => {
      if (!hasUsableFrame(video)) {
        return;
      }
      cleanup();
      resolve();
    };
    for (const event of events) {
      video.addEventListener(event, check);
    }
    timeoutId = window.setTimeout(() => {
      cleanup();
      reject(
        new WebcamError(
          "no-frame",
          "The camera opened but produced no video frames. Close other camera apps and try again.",
        ),
      );
    }, timeoutMs);
  });
}

export async function acquireWebcam(
  options: AcquireWebcamOptions = {},
): Promise<WebcamHandle> {
  const {
    permissionTimeoutMs = CAMERA_PERMISSION_TIMEOUT_MS,
    frameTimeoutMs = CAMERA_FRAME_TIMEOUT_MS,
    createVideo = () => document.createElement("video"),
  } = options;
  if (!window.isSecureContext) {
    throw new WebcamError(
      "insecure-context",
      "Camera access requires a secure (localhost) context.",
    );
  }
  const mediaDevices = (navigator as unknown as { mediaDevices?: MediaDevices })
    .mediaDevices;
  if (mediaDevices === undefined || typeof mediaDevices.getUserMedia !== "function") {
    throw new WebcamError("no-device", "This browser cannot access cameras.");
  }
  let stream: MediaStream;
  let abandoned = false;
  let timeoutId = 0;
  const streamRequest = mediaDevices.getUserMedia({
    video: {
      // Match the learned live-capture envelope. Asking the device for 720p
      // and then shrinking every frame to 640x360 added browser-side latency
      // without supplying the backend any additional pixels.
      width: { exact: 640 },
      height: { exact: 360 },
      frameRate: { ideal: 30 },
    },
    audio: false,
  });
  void streamRequest.then((lateStream) => {
    if (abandoned) {
      for (const track of lateStream.getTracks()) {
        track.stop();
      }
    }
  }).catch(() => {
    // The awaited branch below translates the failure for the UI.
  });
  try {
    stream = await Promise.race([
      streamRequest,
      new Promise<never>((_resolve, reject) => {
        timeoutId = window.setTimeout(() => {
          reject(
            new WebcamError(
              "timeout",
              "Camera permission timed out. Allow camera access, then try again.",
            ),
          );
        }, permissionTimeoutMs);
      }),
    ]);
  } catch (error) {
    abandoned = true;
    if (error instanceof WebcamError) {
      throw error;
    }
    const name = error instanceof DOMException ? error.name : "";
    if (name === "NotAllowedError" || name === "SecurityError") {
      throw new WebcamError("denied", "Camera permission was declined.");
    }
    if (name === "NotFoundError" || name === "OverconstrainedError") {
      throw new WebcamError("no-device", "No usable camera was found.");
    }
    if (name === "NotReadableError" || name === "AbortError") {
      throw new WebcamError("in-use", "The camera is busy in another app.");
    }
    throw new WebcamError("unknown", "The camera could not be started.");
  } finally {
    window.clearTimeout(timeoutId);
  }

  const video = createVideo();
  video.playsInline = true;
  video.muted = true;
  video.srcObject = stream;
  let released = false;
  const release = () => {
    if (released) {
      return;
    }
    released = true;
    for (const track of stream.getTracks()) {
      track.stop();
    }
    video.srcObject = null;
  };
  await video.play().catch(() => {
    // Some browsers resolve playback only after the first frame event. The
    // readiness gate below remains authoritative.
  });
  try {
    await waitForFirstFrame(video, frameTimeoutMs);
  } catch (error) {
    release();
    throw error;
  }
  return { stream, video, release };
}
