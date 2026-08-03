import { afterEach, describe, expect, it, vi } from "vitest";
import {
  encodeFrameEnvelope,
  FRAME_HEADER_BYTES,
} from "@worldstate/contracts/protocol";

import {
  encodeCanvasFrame,
  encodeI420Frame,
  encodeRgbaFrame,
  fitWithin,
} from "./frames";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("fitWithin", () => {
  it("keeps aspect ratio while honoring both limits", () => {
    expect(fitWithin(1920, 1080, 960, 540)).toEqual({ width: 960, height: 540 });
    const tall = fitWithin(1080, 1920, 960, 540);
    expect(tall.height).toBe(540);
    expect(tall.width).toBeLessThanOrEqual(960);
  });

  it("never upscales and produces even dimensions", () => {
    expect(fitWithin(320, 240, 1920, 1080)).toEqual({ width: 320, height: 240 });
    const odd = fitWithin(641, 481, 640, 480);
    expect(odd.width % 2).toBe(0);
    expect(odd.height % 2).toBe(0);
  });

  it("guards degenerate sources", () => {
    expect(fitWithin(0, 0, 640, 480)).toEqual({ width: 2, height: 2 });
  });
});

describe("binary envelope", () => {
  it("writes the exact 28-byte WSF1 big-endian header", () => {
    const payload = new Uint8Array([1, 2, 3, 4]);
    const buffer = encodeFrameEnvelope({
      sequence: 7n,
      capturedAtUnixSeconds: 1_700_000_000.5,
      width: 960,
      height: 540,
      encoding: "jpeg",
      payload,
    });
    expect(buffer.byteLength).toBe(FRAME_HEADER_BYTES + 4);
    const view = new DataView(buffer);
    expect(
      String.fromCharCode(
        view.getUint8(0),
        view.getUint8(1),
        view.getUint8(2),
        view.getUint8(3),
      ),
    ).toBe("WSF1");
    expect(view.getBigUint64(4, false)).toBe(7n);
    expect(view.getFloat64(12, false)).toBeCloseTo(1_700_000_000.5);
    expect(view.getUint16(20, false)).toBe(960);
    expect(view.getUint16(22, false)).toBe(540);
    expect(view.getUint8(24)).toBe(1);
    expect(view.getUint8(25)).toBe(0);
    expect(new Uint8Array(buffer, FRAME_HEADER_BYTES)).toEqual(payload);
  });

  it("uses an offscreen canvas for JPEG encoding when the browser supports it", async () => {
    const drawImage = vi.fn();
    const convertToBlob = vi.fn(() =>
      Promise.resolve(new Blob([new Uint8Array([7, 8, 9])])),
    );
    class FakeOffscreenCanvas {
      width: number;
      height: number;

      constructor(width: number, height: number) {
        this.width = width;
        this.height = height;
      }

      getContext() {
        return { drawImage };
      }

      convertToBlob = convertToBlob;
    }
    vi.stubGlobal("OffscreenCanvas", FakeOffscreenCanvas);
    const canvas = document.createElement("canvas");
    canvas.width = 640;
    canvas.height = 360;
    const toBlob = vi.spyOn(canvas, "toBlob");

    const frame = await encodeCanvasFrame(canvas, 3n, 12.5, 0.65, 100);

    expect(drawImage).toHaveBeenCalledWith(canvas, 0, 0);
    expect(convertToBlob).toHaveBeenCalledWith({
      type: "image/jpeg",
      quality: 0.65,
    });
    expect(toBlob).not.toHaveBeenCalled();
    expect(frame.width).toBe(640);
    expect(frame.height).toBe(360);
    expect(new Uint8Array(frame.buffer, FRAME_HEADER_BYTES)).toEqual(
      new Uint8Array([7, 8, 9]),
    );
  });

  it("packs lossless RGBA pixels when they fit the negotiated frame limit", async () => {
    const rgba = new Uint8ClampedArray([255, 0, 0, 255, 0, 255, 0, 255]);
    const toBlob = vi.fn();
    const canvas = {
      width: 2,
      height: 1,
      getContext: vi.fn(() => ({
        getImageData: vi.fn(() => ({ data: rgba })),
      })),
      toBlob,
    } as unknown as HTMLCanvasElement;

    const frame = await encodeCanvasFrame(canvas, 4n, 13, 0.7, rgba.byteLength);

    expect(new DataView(frame.buffer).getUint8(24)).toBe(3);
    expect(new Uint8Array(frame.buffer, FRAME_HEADER_BYTES)).toEqual(
      new Uint8Array(rgba.buffer),
    );
    expect(toBlob).not.toHaveBeenCalled();
  });

  it("packs a direct VideoFrame RGBA copy without a canvas", () => {
    const rgba = new Uint8Array([255, 0, 0, 255, 0, 255, 0, 255]);
    const frame = encodeRgbaFrame(rgba, 2, 1, 9n, 15.5);

    expect(new DataView(frame.buffer).getUint8(24)).toBe(3);
    expect(new Uint8Array(frame.buffer, FRAME_HEADER_BYTES)).toEqual(rgba);
    expect(() => encodeRgbaFrame(rgba, 3, 1, 10n, 16)).toThrow(
      "RGBA frame length does not match",
    );
  });

  it("packs a direct planar I420 frame", () => {
    const i420 = new Uint8Array((4 * 2 * 3) / 2);
    const frame = encodeI420Frame(i420, 4, 2, 11n, 17.5);

    expect(new DataView(frame.buffer).getUint8(24)).toBe(4);
    expect(new Uint8Array(frame.buffer, FRAME_HEADER_BYTES)).toEqual(i420);
    expect(() => encodeI420Frame(i420, 3, 2, 12n, 18)).toThrow(
      "dimensions must be even",
    );
  });
});
