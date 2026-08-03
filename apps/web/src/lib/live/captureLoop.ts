/**
 * Bounded live capture loop.
 *
 * CAP-003: exactly one frame in flight — the next capture waits for
 * `frame.result` (or a recoverable frame error) before encoding again.
 * CAP-004: busy intervals are counted as skipped, never queued.
 * CAP-006: capture timestamps are real capture times; sequences are
 * monotonic for the lifetime of the loop.
 */

import {
  encodeCanvasFrame,
  encodeI420Frame,
  fitWithin,
  type FrameSource,
} from "./frames";
import type { LiveTransport } from "./transport";

export type CaptureStats = {
  sent: number;
  skipped: number;
  starved: number;
  inFlight: boolean;
  lastSequence: number;
  /** Browser-local capture-to-result time; never compares host clocks. */
  lastCaptureToResultMs: number | null;
  lastEncodeMs: number | null;
  lastResultToCaptureMs: number | null;
};

export type CaptureLoopOptions = {
  transport: LiveTransport;
  source: FrameSource;
  maxWidth: number;
  maxHeight: number;
  intervalMs?: number;
  jpegQuality?: number;
  maxFrameBytes?: number;
  onTick?: (canvas: HTMLCanvasElement, stats: CaptureStats) => void;
  /** Injection points for tests. */
  now?: () => number;
  monotonicNow?: () => number;
  encode?: typeof encodeCanvasFrame;
  createCanvas?: () => HTMLCanvasElement;
};

export type CaptureLoop = {
  start: () => void;
  stop: () => void;
  readonly stats: CaptureStats;
  /** Manually run one capture tick (used by tests and by paused states). */
  tick: () => Promise<void>;
};

export function createCaptureLoop(options: CaptureLoopOptions): CaptureLoop {
  const {
    transport,
    source,
    maxWidth,
    maxHeight,
    intervalMs = 1000 / 30,
    jpegQuality = 0.7,
    maxFrameBytes = Number.POSITIVE_INFINITY,
    onTick,
    now = () => Date.now(),
    monotonicNow = () => performance.now(),
    encode = encodeCanvasFrame,
    createCanvas = () => document.createElement("canvas"),
  } = options;

  const canvas = createCanvas();
  const stats: CaptureStats = {
    sent: 0,
    skipped: 0,
    starved: 0,
    inFlight: false,
    lastSequence: -1,
    lastCaptureToResultMs: null,
    lastEncodeMs: null,
    lastResultToCaptureMs: null,
  };

  let sequence = 0n;
  let timer: number | null = null;
  let pausedUntil = 0;
  let lastCaptureAt: number | null = null;
  let inFlightStartedAt: number | null = null;
  let lastResultAt: number | null = null;
  let directI420Disabled = false;
  // The running flag can flip during encoding when stop() is called
  // mid-flight, so it is always re-read through this accessor.
  const flags = { running: false };
  const isRunning = () => flags.running;

  function scheduleNext(delayMs: number): void {
    if (!isRunning()) {
      return;
    }
    if (timer !== null) {
      window.clearTimeout(timer);
    }
    timer = window.setTimeout(() => {
      timer = null;
      void tick();
    }, Math.max(0, delayMs));
  }

  function resumeAtCadence(): void {
    if (lastCaptureAt === null) {
      scheduleNext(0);
      return;
    }
    const elapsed = Math.max(0, now() - lastCaptureAt);
    const missed = Math.max(0, Math.floor(elapsed / intervalMs) - 1);
    stats.skipped += missed;
    if (elapsed >= intervalMs) {
      // A result that arrives after the target cadence is already permission
      // to capture again. Start directly from the socket callback; an extra
      // browser task boundary added a material result-to-capture bubble in the
      // real webcam path. The in-flight flag is cleared before this call, so
      // CAP-003 remains intact.
      if (isRunning() && !stats.inFlight) {
        void tick();
      }
      return;
    }
    scheduleNext(intervalMs - elapsed);
  }

  const unsubscribe = transport.subscribe((message) => {
    if (message.type === "frame.result") {
      const resultAt = monotonicNow();
      if (inFlightStartedAt !== null) {
        stats.lastCaptureToResultMs = Math.max(
          0,
          resultAt - inFlightStartedAt,
        );
      }
      lastResultAt = resultAt;
      inFlightStartedAt = null;
      stats.inFlight = false;
      stats.lastSequence = message.sequence;
      resumeAtCadence();
    } else if (message.type === "flow.slow_down") {
      pausedUntil = now() + message.retry_after_ms;
      inFlightStartedAt = null;
      stats.inFlight = false;
      scheduleNext(message.retry_after_ms);
    } else if (message.type === "error" && message.recoverable) {
      // e.g. invalid_frame: release the slot so the loop can continue.
      inFlightStartedAt = null;
      stats.inFlight = false;
      resumeAtCadence();
    }
  });

  async function tick(): Promise<void> {
    if (!isRunning()) {
      return;
    }
    if (lastResultAt !== null) {
      stats.lastResultToCaptureMs = Math.max(0, monotonicNow() - lastResultAt);
      lastResultAt = null;
    }
    if (stats.inFlight) {
      stats.skipped += 1;
      return;
    }
    if (now() < pausedUntil) {
      stats.skipped += 1;
      scheduleNext(pausedUntil - now());
      return;
    }
    const size = fitWithin(
      source.nativeWidth,
      source.nativeHeight,
      maxWidth,
      maxHeight,
    );
    const directI420 = source.captureI420;
    const directByteLength = (size.width * size.height * 3) / 2;
    if (
      !directI420Disabled &&
      directI420 !== undefined &&
      directByteLength <= maxFrameBytes
    ) {
      stats.inFlight = true;
      inFlightStartedAt = monotonicNow();
      lastCaptureAt = now();
      const capturedAt = lastCaptureAt / 1000;
      const currentSequence = sequence;
      sequence += 1n;
      try {
        const encodeStartedAt = monotonicNow();
        const i420 = await directI420(size.width, size.height);
        if (i420 === null) {
          stats.starved += 1;
          inFlightStartedAt = null;
          stats.inFlight = false;
          scheduleNext(intervalMs);
          return;
        }
        const frame = encodeI420Frame(
          i420,
          size.width,
          size.height,
          currentSequence,
          capturedAt,
        );
        stats.lastEncodeMs = Math.max(0, monotonicNow() - encodeStartedAt);
        if (!isRunning()) {
          inFlightStartedAt = null;
          stats.inFlight = false;
          return;
        }
        transport.sendFrame(frame.buffer);
        stats.sent += 1;
        onTick?.(canvas, stats);
      } catch {
        // A browser may expose VideoFrame without supporting I420 conversion
        // for this camera format. Fail over once to the proven canvas path.
        directI420Disabled = true;
        inFlightStartedAt = null;
        stats.inFlight = false;
        resumeAtCadence();
      }
      return;
    }
    if (canvas.width !== size.width || canvas.height !== size.height) {
      canvas.width = size.width;
      canvas.height = size.height;
    }
    const context =
      canvas.getContext("2d", { alpha: false, willReadFrequently: true }) ?? null;
    if (context === null) {
      scheduleNext(intervalMs);
      return;
    }
    if (!source.draw(context, size.width, size.height)) {
      stats.starved += 1;
      scheduleNext(intervalMs);
      return;
    }
    stats.inFlight = true;
    inFlightStartedAt = monotonicNow();
    lastCaptureAt = now();
    const capturedAt = lastCaptureAt / 1000;
    const currentSequence = sequence;
    sequence += 1n;
    try {
      const encodeStartedAt = monotonicNow();
      const frame = await encode(
        canvas,
        currentSequence,
        capturedAt,
        jpegQuality,
        maxFrameBytes,
      );
      stats.lastEncodeMs = Math.max(0, monotonicNow() - encodeStartedAt);
      if (!isRunning()) {
        inFlightStartedAt = null;
        stats.inFlight = false;
        return;
      }
      transport.sendFrame(frame.buffer);
      stats.sent += 1;
      onTick?.(canvas, stats);
    } catch {
      inFlightStartedAt = null;
      stats.inFlight = false;
      resumeAtCadence();
    }
  }

  return {
    stats,
    tick,
    start() {
      if (flags.running) {
        return;
      }
      flags.running = true;
      scheduleNext(intervalMs);
    },
    stop() {
      flags.running = false;
      if (timer !== null) {
        window.clearTimeout(timer);
        timer = null;
      }
      unsubscribe();
      inFlightStartedAt = null;
      stats.inFlight = false;
    },
  };
}
