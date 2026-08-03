import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { encodeFrameEnvelope } from "@worldstate/contracts/protocol";

import { MockTransport } from "./mockTransport";
import type { ServerMessage } from "../../protocol/messages";

function frameBuffer(sequence: bigint): ArrayBuffer {
  return encodeFrameEnvelope({
    sequence,
    capturedAtUnixSeconds: Date.now() / 1000,
    width: 960,
    height: 540,
    encoding: "jpeg",
    payload: new Uint8Array([255, 216, 255]),
  });
}

describe("MockTransport", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("answers the handshake with a replay server.ready", async () => {
    const transport = new MockTransport();
    const readyPromise = transport.connect();
    await vi.advanceTimersByTimeAsync(200);
    const ready = await readyPromise;
    expect(ready.type).toBe("server.ready");
    expect(ready.provider_mode).toBe("replay");
    expect(ready.limits.max_frame_bytes).toBeGreaterThan(0);
  });

  it("emits world.patch, event.batch, then frame.result per frame", async () => {
    const transport = new MockTransport();
    const messages: ServerMessage[] = [];
    transport.subscribe((message) => messages.push(message));

    transport.sendFrame(frameBuffer(0n));
    await vi.advanceTimersByTimeAsync(100);

    expect(messages.map((message) => message.type)).toEqual([
      "world.patch",
      "event.batch",
      "frame.result",
    ]);
    const result = messages[2];
    if (result?.type === "frame.result") {
      expect(result.sequence).toBe(0);
      expect(result.objects).toHaveLength(3);
      expect(result.metrics.queue_depth).toBe(0);
    }
  });

  it("tracks dropped frames from sequence gaps", async () => {
    const transport = new MockTransport();
    const messages: ServerMessage[] = [];
    transport.subscribe((message) => messages.push(message));

    transport.sendFrame(frameBuffer(0n));
    await vi.advanceTimersByTimeAsync(100);
    transport.sendFrame(frameBuffer(5n));
    await vi.advanceTimersByTimeAsync(100);

    const last = messages[messages.length - 1];
    if (last?.type === "frame.result") {
      expect(last.metrics.dropped_frames).toBe(4);
      expect(last.sequence).toBe(5);
    } else {
      throw new Error("expected a frame.result");
    }
  });

  it("answers last-seen queries from observed history", async () => {
    const transport = new MockTransport();
    transport.subscribe(() => undefined);
    transport.sendFrame(frameBuffer(0n));
    await vi.advanceTimersByTimeAsync(100);

    const resultPromise = transport.submitCommand({
      command: "find_last_seen",
      sceneId: "s".repeat(36),
      entityId: "01900000-0000-7000-8000-0000000000e0",
    });
    await vi.advanceTimersByTimeAsync(50);
    const result = await resultPromise;
    expect(result.status).toBe("completed");
    expect(result.result?.label).toBe("cup");
    expect(result.result?.last_seen_at).toBeTruthy();
  });

  it("stops emitting after close", async () => {
    const transport = new MockTransport();
    const messages: ServerMessage[] = [];
    transport.subscribe((message) => messages.push(message));
    transport.sendFrame(frameBuffer(0n));
    transport.close();
    await vi.advanceTimersByTimeAsync(200);
    expect(messages).toHaveLength(0);
  });
});
