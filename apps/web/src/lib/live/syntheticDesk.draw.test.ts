import { afterEach, describe, expect, it, vi } from "vitest";

import { createSyntheticDesk, videoFrameSource } from "./syntheticDesk";

/** Minimal 2D-context stub sufficient for the desk painter. */
function stubContext(): CanvasRenderingContext2D {
  const gradient = { addColorStop: vi.fn() };
  const stub = {
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 0,
    globalAlpha: 1,
    createLinearGradient: vi.fn(() => gradient),
    createRadialGradient: vi.fn(() => gradient),
    fillRect: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    bezierCurveTo: vi.fn(),
    stroke: vi.fn(),
    fill: vi.fn(),
    ellipse: vi.fn(),
    roundRect: vi.fn(),
    arc: vi.fn(),
    translate: vi.fn(),
    rotate: vi.fn(),
    drawImage: vi.fn(),
  };
  return stub as unknown as CanvasRenderingContext2D;
}

describe("createSyntheticDesk", () => {
  it("paints every frame across the full replay without faulting", () => {
    const desk = createSyntheticDesk();
    const context = stubContext();
    for (let i = 0; i < 60; i += 1) {
      expect(desk.draw(context, 960, 540)).toBe(true);
      desk.advance();
    }
    expect(desk.nativeWidth).toBe(640);
    expect(desk.nativeHeight).toBe(360);
  });
});

describe("videoFrameSource", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("reports starvation until the video has data", () => {
    const video = {
      readyState: 0,
      videoWidth: 0,
      videoHeight: 0,
    } as HTMLVideoElement;
    const source = videoFrameSource(video);
    expect(source.draw(stubContext(), 640, 360)).toBe(false);
    expect(source.nativeWidth).toBe(1280);
    expect(source.nativeHeight).toBe(720);
  });

  it("draws once frames are available and reports native size", () => {
    const video = {
      readyState: 4,
      videoWidth: 1920,
      videoHeight: 1080,
    } as HTMLVideoElement;
    const source = videoFrameSource(video);
    const drawImage = vi.fn();
    const context = {
      ...(stubContext() as unknown as Record<string, unknown>),
      drawImage,
    } as unknown as CanvasRenderingContext2D;
    expect(source.draw(context, 640, 360)).toBe(true);
    expect(drawImage).toHaveBeenCalledWith(video, 0, 0, 640, 360);
    expect(source.nativeWidth).toBe(1920);
  });

  it("copies a native video frame directly to I420", async () => {
    const close = vi.fn();
    const copyTo = vi.fn((target: Uint8Array) => {
      target.fill(128);
      return Promise.resolve([]);
    });
    vi.stubGlobal(
      "VideoFrame",
      class {
        copyTo = copyTo;
        close = close;
      },
    );
    const video = {
      readyState: 4,
      videoWidth: 640,
      videoHeight: 360,
    } as HTMLVideoElement;

    const result = await videoFrameSource(video).captureI420?.(640, 360);

    expect(result).toHaveLength((640 * 360 * 3) / 2);
    expect(copyTo).toHaveBeenCalledOnce();
    expect(close).toHaveBeenCalledOnce();
  });
});
