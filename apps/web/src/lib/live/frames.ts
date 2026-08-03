/** Binary frame packaging for the live WebSocket (WSF1 envelope). */

import { encodeFrameEnvelope } from "@worldstate/contracts/protocol";

export type EncodedFrame = {
  buffer: ArrayBuffer;
  width: number;
  height: number;
  byteLength: number;
  capturedAtUnixSeconds: number;
  sequence: bigint;
};

export type FrameSource = {
  /** Draw the current frame into the context; returns false when starved. */
  draw: (
    context: CanvasRenderingContext2D,
    width: number,
    height: number,
  ) => boolean;
  /** Optional zero-canvas path for a native-size real video frame. */
  captureI420?: (width: number, height: number) => Promise<Uint8Array | null>;
  readonly nativeWidth: number;
  readonly nativeHeight: number;
};

const offscreenEncoders = new WeakMap<HTMLCanvasElement, OffscreenCanvas>();

async function encodeJpeg(
  canvas: HTMLCanvasElement,
  quality: number,
): Promise<Blob | null> {
  if (typeof globalThis.OffscreenCanvas === "function") {
    let offscreen = offscreenEncoders.get(canvas);
    if (offscreen === undefined) {
      offscreen = new globalThis.OffscreenCanvas(canvas.width, canvas.height);
      offscreenEncoders.set(canvas, offscreen);
    }
    if (offscreen.width !== canvas.width || offscreen.height !== canvas.height) {
      offscreen.width = canvas.width;
      offscreen.height = canvas.height;
    }
    const context = offscreen.getContext("2d", { alpha: false });
    if (context !== null) {
      context.drawImage(canvas, 0, 0);
      return offscreen.convertToBlob({ type: "image/jpeg", quality });
    }
  }

  return new Promise<Blob | null>((resolve) => {
    canvas.toBlob(resolve, "image/jpeg", quality);
  });
}

export function encodeRgbaFrame(
  rgba: Uint8Array,
  width: number,
  height: number,
  sequence: bigint,
  capturedAtUnixSeconds: number,
): EncodedFrame {
  if (rgba.byteLength !== width * height * 4) {
    throw new Error("RGBA frame length does not match its dimensions");
  }
  const buffer = encodeFrameEnvelope({
    sequence,
    capturedAtUnixSeconds,
    width,
    height,
    encoding: "rgba",
    payload: rgba,
  });
  return {
    buffer,
    width,
    height,
    byteLength: buffer.byteLength,
    capturedAtUnixSeconds,
    sequence,
  };
}

export function encodeI420Frame(
  i420: Uint8Array,
  width: number,
  height: number,
  sequence: bigint,
  capturedAtUnixSeconds: number,
): EncodedFrame {
  if (width % 2 !== 0 || height % 2 !== 0) {
    throw new Error("I420 frame dimensions must be even");
  }
  if (i420.byteLength !== (width * height * 3) / 2) {
    throw new Error("I420 frame length does not match its dimensions");
  }
  const buffer = encodeFrameEnvelope({
    sequence,
    capturedAtUnixSeconds,
    width,
    height,
    encoding: "i420",
    payload: i420,
  });
  return {
    buffer,
    width,
    height,
    byteLength: buffer.byteLength,
    capturedAtUnixSeconds,
    sequence,
  };
}

function readRgba(canvas: HTMLCanvasElement): Uint8Array | null {
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (context === null) {
    return null;
  }
  const rgba = context.getImageData(0, 0, canvas.width, canvas.height).data;
  return new Uint8Array(rgba.buffer, rgba.byteOffset, rgba.byteLength);
}

/** Fit source dimensions into limits while preserving aspect ratio. */
export function fitWithin(
  width: number,
  height: number,
  maxWidth: number,
  maxHeight: number,
): { width: number; height: number } {
  if (width <= 0 || height <= 0) {
    return { width: 2, height: 2 };
  }
  const scale = Math.min(1, maxWidth / width, maxHeight / height);
  return {
    width: Math.max(2, Math.round(width * scale) & ~1),
    height: Math.max(2, Math.round(height * scale) & ~1),
  };
}

export async function encodeCanvasFrame(
  canvas: HTMLCanvasElement,
  sequence: bigint,
  capturedAtUnixSeconds: number,
  quality = 0.7,
  maximumBytes = Number.POSITIVE_INFINITY,
): Promise<EncodedFrame> {
  const rawByteLength = canvas.width * canvas.height * 4;
  const rgba = rawByteLength <= maximumBytes ? readRgba(canvas) : null;
  let encoding: "jpeg" | "rgba";
  let payload: Uint8Array;
  if (rgba !== null && rgba.byteLength <= maximumBytes) {
    encoding = "rgba";
    payload = rgba;
  } else {
    const blob = await encodeJpeg(canvas, quality);
    if (blob === null) {
      throw new Error("frame encoding produced no data");
    }
    if (blob.size > maximumBytes) {
      throw new Error("frame encoding exceeds the configured limit");
    }
    encoding = "jpeg";
    payload = new Uint8Array(await blob.arrayBuffer());
  }
  const buffer = encodeFrameEnvelope({
    sequence,
    capturedAtUnixSeconds,
    width: canvas.width,
    height: canvas.height,
    encoding,
    payload,
  });
  return {
    buffer,
    width: canvas.width,
    height: canvas.height,
    byteLength: buffer.byteLength,
    capturedAtUnixSeconds,
    sequence,
  };
}
