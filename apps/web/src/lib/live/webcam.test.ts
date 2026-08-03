import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { acquireWebcam, WebcamError } from "./webcam";

function setMediaDevices(getUserMedia: ReturnType<typeof vi.fn> | undefined): void {
  Object.defineProperty(navigator, "mediaDevices", {
    configurable: true,
    value: getUserMedia === undefined ? undefined : { getUserMedia },
  });
}

function fakeStream(stop = vi.fn()): MediaStream {
  return {
    getTracks: () => [{ stop }],
  } as unknown as MediaStream;
}

function fakeVideo({ ready = true }: { ready?: boolean } = {}): HTMLVideoElement {
  const video = document.createElement("video");
  Object.defineProperties(video, {
    readyState: { configurable: true, value: ready ? 2 : 0 },
    videoWidth: { configurable: true, value: ready ? 1280 : 0 },
    videoHeight: { configurable: true, value: ready ? 720 : 0 },
  });
  return video;
}

describe("acquireWebcam", () => {
  beforeEach(() => {
    Object.defineProperty(window, "isSecureContext", {
      configurable: true,
      value: true,
    });
    vi.spyOn(HTMLMediaElement.prototype, "play").mockResolvedValue();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("requests the native live-capture size and releases every track exactly once", async () => {
    const stop = vi.fn();
    const getUserMedia = vi.fn().mockResolvedValue(fakeStream(stop));
    setMediaDevices(getUserMedia);

    const handle = await acquireWebcam({ createVideo: () => fakeVideo() });
    expect(getUserMedia).toHaveBeenCalledWith({
      video: {
        width: { exact: 640 },
        height: { exact: 360 },
        frameRate: { ideal: 30 },
      },
      audio: false,
    });
    expect(handle.video.srcObject).toBe(handle.stream);

    handle.release();
    handle.release();
    expect(stop).toHaveBeenCalledTimes(1);
    expect(handle.video.srcObject).toBeNull();
  });

  it.each([
    ["NotAllowedError", "denied"],
    ["NotFoundError", "no-device"],
    ["NotReadableError", "in-use"],
    ["UnexpectedError", "unknown"],
  ] as const)("maps %s into %s", async (domName, reason) => {
    setMediaDevices(
      vi.fn().mockRejectedValue(new DOMException("camera failure", domName)),
    );

    const failure = await acquireWebcam().catch((error: unknown) => error);
    expect(failure).toBeInstanceOf(WebcamError);
    expect((failure as WebcamError).reason).toBe(reason);
  });

  it("rejects unsupported and insecure browser contexts", async () => {
    Object.defineProperty(window, "isSecureContext", {
      configurable: true,
      value: false,
    });
    await expect(acquireWebcam()).rejects.toMatchObject({
      reason: "insecure-context",
    });

    Object.defineProperty(window, "isSecureContext", {
      configurable: true,
      value: true,
    });
    setMediaDevices(undefined);
    await expect(acquireWebcam()).rejects.toMatchObject({ reason: "no-device" });
  });

  it("times out unanswered permission and stops a stream that resolves late", async () => {
    vi.useFakeTimers();
    let resolveStream: ((stream: MediaStream) => void) | undefined;
    const request = new Promise<MediaStream>((resolve) => {
      resolveStream = resolve;
    });
    setMediaDevices(vi.fn().mockReturnValue(request));
    const stop = vi.fn();

    const pending = acquireWebcam();
    const rejection = expect(pending).rejects.toMatchObject({ reason: "timeout" });
    await vi.advanceTimersByTimeAsync(20_000);
    await rejection;

    resolveStream?.(fakeStream(stop));
    await Promise.resolve();
    expect(stop).toHaveBeenCalledOnce();
  });

  it("fails before backend startup when a camera stream never yields a frame", async () => {
    vi.useFakeTimers();
    const stop = vi.fn();
    setMediaDevices(vi.fn().mockResolvedValue(fakeStream(stop)));

    const pending = acquireWebcam({
      createVideo: () => fakeVideo({ ready: false }),
      frameTimeoutMs: 250,
    });
    const rejection = expect(pending).rejects.toMatchObject({ reason: "no-frame" });
    await vi.advanceTimersByTimeAsync(250);
    await rejection;

    expect(stop).toHaveBeenCalledOnce();
  });
});
