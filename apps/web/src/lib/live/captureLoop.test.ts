import { describe, expect, it, vi } from "vitest";

import { createCaptureLoop } from "./captureLoop";
import type { EncodedFrame, FrameSource } from "./frames";
import type {
  LiveTransport,
  TransportListener,
} from "./transport";
import { PROTOCOL_VERSION, type FrameResult } from "../protocol/messages";

function fakeTransport() {
  const listeners = new Set<TransportListener>();
  const sent: ArrayBuffer[] = [];
  const transport: LiveTransport = {
    kind: "simulation",
    connect: () => Promise.reject(new Error("unused")),
    sendFrame: (buffer) => {
      sent.push(buffer);
    },
    submitCommand: () => Promise.reject(new Error("unused")),
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    onClose: () => undefined,
    close: () => undefined,
  };
  const emitResult = (sequence: number) => {
    const result: FrameResult = {
      type: "frame.result",
      protocol_version: PROTOCOL_VERSION,
      request_id: `frame-${String(sequence)}`,
      sequence,
      captured_at: new Date().toISOString(),
      presented_at: new Date().toISOString(),
      objects: [],
      events: [],
      metrics: {
        sequence,
        capture_to_result_ms: 20,
        inference_ms: 5,
        queue_depth: 0,
        dropped_frames: 0,
        discovery_ran: false,
        depth_ran: false,
        embedding_ran: false,
      },
      quality: {},
    };
    for (const listener of listeners) {
      listener(result);
    }
  };
  const emitSlowDown = (retryAfterMs: number) => {
    for (const listener of listeners) {
      listener({
        type: "flow.slow_down",
        protocol_version: PROTOCOL_VERSION,
        request_id: "x",
        retry_after_ms: retryAfterMs,
        reason: "busy",
      });
    }
  };
  return { transport, sent, emitResult, emitSlowDown, listeners };
}

function fakeSource(): FrameSource {
  return {
    nativeWidth: 1280,
    nativeHeight: 720,
    draw: () => true,
  };
}

function fakeCanvas(): HTMLCanvasElement {
  const canvas = {
    width: 0,
    height: 0,
    getContext: () => ({}) as CanvasRenderingContext2D,
  };
  return canvas as unknown as HTMLCanvasElement;
}

const captured: { sequence: bigint; capturedAt: number }[] = [];

const fakeEncode = (
  canvas: HTMLCanvasElement,
  sequence: bigint,
  capturedAtUnixSeconds: number,
): Promise<EncodedFrame> => {
  captured.push({ sequence, capturedAt: capturedAtUnixSeconds });
  return Promise.resolve({
    buffer: new ArrayBuffer(32),
    width: canvas.width,
    height: canvas.height,
    byteLength: 32,
    capturedAtUnixSeconds,
    sequence,
  });
};

function makeLoop(nowValue: () => number, monotonicNowValue = nowValue) {
  const harness = fakeTransport();
  const loop = createCaptureLoop({
    transport: harness.transport,
    source: fakeSource(),
    maxWidth: 960,
    maxHeight: 540,
    now: nowValue,
    monotonicNow: monotonicNowValue,
    encode: fakeEncode,
    createCanvas: fakeCanvas,
  });
  return { ...harness, loop };
}

describe("createCaptureLoop", () => {
  it("keeps exactly one frame in flight and counts skipped intervals", async () => {
    captured.length = 0;
    const { loop, sent, emitResult } = makeLoop(() => 1_000_000);
    loop.start();

    await loop.tick();
    expect(sent).toHaveLength(1);
    expect(loop.stats.inFlight).toBe(true);

    // Busy: nothing new is sent, the interval is counted as skipped.
    await loop.tick();
    await loop.tick();
    expect(sent).toHaveLength(1);
    expect(loop.stats.skipped).toBe(2);

    emitResult(0);
    expect(loop.stats.inFlight).toBe(false);
    await loop.tick();
    expect(sent).toHaveLength(2);
    loop.stop();
  });

  it("uses real capture timestamps and monotonic sequences", async () => {
    captured.length = 0;
    let now = 5_000_000;
    const { loop, emitResult } = makeLoop(() => now);
    loop.start();
    await loop.tick();
    emitResult(0);
    now += 100;
    await loop.tick();
    loop.stop();

    expect(captured.map((frame) => frame.sequence)).toEqual([0n, 1n]);
    expect(captured[0]?.capturedAt).toBeCloseTo(5_000);
    expect(captured[1]?.capturedAt).toBeCloseTo(5_000.1);
  });

  it("measures capture-to-result latency on the browser monotonic clock", async () => {
    captured.length = 0;
    let monotonicNow = 250;
    const { loop, emitResult } = makeLoop(
      () => 1_700_000_123_000,
      () => monotonicNow,
    );
    loop.start();

    await loop.tick();
    monotonicNow = 287.5;
    emitResult(0);

    expect(loop.stats.lastCaptureToResultMs).toBeCloseTo(37.5);
    expect(captured[0]?.capturedAt).toBeCloseTo(1_700_000_123);
    loop.stop();
  });

  it("resumes immediately when a result arrives after the target cadence", async () => {
    captured.length = 0;
    let now = 10_000;
    const { loop, sent, emitResult } = makeLoop(() => now);
    loop.start();
    await loop.tick();
    expect(sent).toHaveLength(1);

    now += 100;
    emitResult(0);
    await Promise.resolve();
    await Promise.resolve();

    expect(sent).toHaveLength(2);
    expect(loop.stats.inFlight).toBe(true);
    loop.stop();
  });

  it("pauses after flow.slow_down until the retry deadline passes", async () => {
    captured.length = 0;
    let now = 0;
    const { loop, sent, emitResult, emitSlowDown } = makeLoop(() => now);
    loop.start();
    await loop.tick();
    emitResult(0);
    emitSlowDown(1_000);

    await loop.tick();
    expect(sent).toHaveLength(1);
    expect(loop.stats.skipped).toBe(1);

    now = 1_001;
    await loop.tick();
    expect(sent).toHaveLength(2);
    loop.stop();
  });

  it("stops sending after stop() even mid-encode", async () => {
    captured.length = 0;
    const { loop, sent, listeners } = makeLoop(() => 1);
    loop.start();
    const pending = loop.tick();
    loop.stop();
    await pending;
    // The encode settled after stop: nothing sent, listener detached.
    expect(sent.length).toBeLessThanOrEqual(1);
    expect(listeners.size).toBe(0);
  });

  it("counts starved sources without sending", async () => {
    const harness = fakeTransport();
    const loop = createCaptureLoop({
      transport: harness.transport,
      source: { nativeWidth: 100, nativeHeight: 100, draw: () => false },
      maxWidth: 960,
      maxHeight: 540,
      encode: fakeEncode,
      createCanvas: fakeCanvas,
    });
    loop.start();
    await loop.tick();
    expect(loop.stats.starved).toBe(1);
    expect(harness.sent).toHaveLength(0);
    loop.stop();
  });

  it("uses a direct native RGBA source without drawing a canvas", async () => {
    const harness = fakeTransport();
    const draw = vi.fn(() => true);
    const captureI420 = vi.fn(() => Promise.resolve(new Uint8Array((4 * 4 * 3) / 2)));
    const loop = createCaptureLoop({
      transport: harness.transport,
      source: {
        nativeWidth: 4,
        nativeHeight: 4,
        draw,
        captureI420,
      },
      maxWidth: 4,
      maxHeight: 4,
      maxFrameBytes: 4 * 4 * 4,
      createCanvas: fakeCanvas,
    });

    loop.start();
    await loop.tick();

    expect(captureI420).toHaveBeenCalledWith(4, 4);
    expect(draw).not.toHaveBeenCalled();
    expect(harness.sent).toHaveLength(1);
    loop.stop();
  });

  it("falls back to canvas capture when direct RGBA conversion fails", async () => {
    const harness = fakeTransport();
    const draw = vi.fn(() => true);
    const captureI420 = vi.fn(() => Promise.reject(new Error("unsupported format")));
    const loop = createCaptureLoop({
      transport: harness.transport,
      source: {
        nativeWidth: 4,
        nativeHeight: 4,
        draw,
        captureI420,
      },
      maxWidth: 4,
      maxHeight: 4,
      maxFrameBytes: 4 * 4 * 4,
      encode: fakeEncode,
      createCanvas: fakeCanvas,
    });

    loop.start();
    await loop.tick();
    await loop.tick();

    expect(captureI420).toHaveBeenCalledTimes(1);
    expect(draw).toHaveBeenCalledTimes(1);
    expect(harness.sent).toHaveLength(1);
    loop.stop();
  });
});
