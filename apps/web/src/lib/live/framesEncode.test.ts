import { describe, expect, it } from "vitest";
import { FRAME_HEADER_BYTES } from "@worldstate/contracts/protocol";

import { encodeCanvasFrame } from "./frames";

function fakeCanvas(blob: Blob | null): HTMLCanvasElement {
  return {
    width: 320,
    height: 180,
    getContext: () => null,
    toBlob: (callback: (result: Blob | null) => void) => {
      callback(blob);
    },
  } as unknown as HTMLCanvasElement;
}

describe("encodeCanvasFrame", () => {
  it("wraps the encoded image in a WSF1 envelope", async () => {
    const payload = new Uint8Array([0xff, 0xd8, 0xff, 0xe0]);
    const canvas = fakeCanvas(new Blob([payload]));
    const frame = await encodeCanvasFrame(canvas, 3n, 1_700_000_123.25);
    expect(frame.byteLength).toBe(FRAME_HEADER_BYTES + payload.byteLength);
    expect(frame.width).toBe(320);
    expect(frame.height).toBe(180);
    expect(frame.sequence).toBe(3n);
    const view = new DataView(frame.buffer);
    expect(view.getBigUint64(4, false)).toBe(3n);
    expect(view.getFloat64(12, false)).toBeCloseTo(1_700_000_123.25);
    expect(view.getUint8(24)).toBe(1);
  });

  it("throws when the browser produces no image data", async () => {
    await expect(
      encodeCanvasFrame(fakeCanvas(null), 0n, 1),
    ).rejects.toThrow(/no data/);
  });
});
