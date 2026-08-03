/** Framework-neutral helpers for WorldState protocol v1. */

export const WORLDSTATE_PROTOCOL_VERSION = "v1" as const;
export const FRAME_MAGIC = "WSF1" as const;
export const FRAME_HEADER_BYTES = 28;

export type FrameEncoding = "jpeg" | "webp" | "rgba" | "i420";

export interface FrameEnvelope {
  sequence: bigint;
  capturedAtUnixSeconds: number;
  width: number;
  height: number;
  encoding: FrameEncoding;
  payload: Uint8Array;
}

export function encodeFrameEnvelope(frame: FrameEnvelope): ArrayBuffer {
  const output = new ArrayBuffer(FRAME_HEADER_BYTES + frame.payload.byteLength);
  const view = new DataView(output);
  for (let index = 0; index < FRAME_MAGIC.length; index += 1) {
    view.setUint8(index, FRAME_MAGIC.charCodeAt(index));
  }
  view.setBigUint64(4, frame.sequence, false);
  view.setFloat64(12, frame.capturedAtUnixSeconds, false);
  view.setUint16(20, frame.width, false);
  view.setUint16(22, frame.height, false);
  const encodingCode =
    frame.encoding === "jpeg"
      ? 1
      : frame.encoding === "webp"
        ? 2
        : frame.encoding === "rgba"
          ? 3
          : 4;
  view.setUint8(24, encodingCode);
  new Uint8Array(output, FRAME_HEADER_BYTES).set(frame.payload);
  return output;
}

export function isWorldStateMessage(value: unknown): value is { type: string } {
  return (
    typeof value === "object" &&
    value !== null &&
    "type" in value &&
    typeof (value as { type?: unknown }).type === "string"
  );
}
