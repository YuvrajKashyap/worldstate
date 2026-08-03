import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WsTransport } from "./transport";
import type { ClientHello, CommandSubmit } from "../protocol/messages";

class FakeWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;
  static instances: FakeWebSocket[] = [];

  binaryType = "blob";
  readyState = FakeWebSocket.CONNECTING;
  sent: (string | ArrayBuffer)[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<unknown>) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  send(data: string | ArrayBuffer): void {
    this.sent.push(data);
  }

  close(_code?: number, reason?: string): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ reason: reason ?? "" } as CloseEvent);
  }

  simulateOpen(): void {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }

  simulateMessage(payload: unknown): void {
    this.onmessage?.({ data: JSON.stringify(payload) } as MessageEvent<unknown>);
  }

  simulateServerClose(reason: string): void {
    this.readyState = FakeWebSocket.CLOSED;
    this.onclose?.({ reason } as CloseEvent);
  }
}

const READY = {
  type: "server.ready",
  protocol_version: "v1",
  request_id: "r",
  accepted_capabilities: ["frame.result"],
  provider_mode: "replay",
  limits: {
    max_frame_bytes: 1,
    max_frame_width: 1,
    max_frame_height: 1,
    max_upload_bytes: 1,
    max_video_duration_seconds: 1,
    max_pending_jobs: 1,
    storage_quota_bytes: 1,
  },
};

describe("WsTransport", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function connect() {
    const transport = new WsTransport("ws://127.0.0.1:8000/api/v1/live");
    const promise = transport.connect("s".repeat(36), ["cup"]);
    const socket = FakeWebSocket.instances[0];
    if (socket === undefined) {
      throw new Error("socket not created");
    }
    return { transport, promise, socket };
  }

  it("sends a valid hello and resolves on server.ready", async () => {
    const { promise, socket } = connect();
    socket.simulateOpen();
    expect(socket.binaryType).toBe("arraybuffer");
    const hello = JSON.parse(socket.sent[0] as string) as ClientHello;
    expect(hello.type).toBe("client.hello");
    expect(hello.protocol_version).toBe("v1");
    expect(hello.session_id).toBe("s".repeat(36));
    expect(hello.prompts).toEqual(["cup"]);

    socket.simulateMessage(READY);
    const ready = await promise;
    expect(ready.provider_mode).toBe("replay");
  });

  it("rejects the handshake on protocol errors", async () => {
    const { promise, socket } = connect();
    socket.simulateOpen();
    socket.simulateMessage({
      type: "error",
      protocol_version: "v1",
      request_id: null,
      code: "invalid_session",
      message: "A live or replay capture session is required.",
      recoverable: false,
    });
    await expect(promise).rejects.toThrow(/capture session/);
  });

  it("rejects when the server is busy (flow.slow_down)", async () => {
    const { promise, socket } = connect();
    socket.simulateOpen();
    socket.simulateMessage({
      type: "flow.slow_down",
      protocol_version: "v1",
      request_id: "r",
      retry_after_ms: 1000,
      reason: "busy",
    });
    await expect(promise).rejects.toThrow(/busy/);
  });

  it("dispatches post-handshake messages to subscribers", async () => {
    const { transport, promise, socket } = connect();
    socket.simulateOpen();
    socket.simulateMessage(READY);
    await promise;

    const seen: string[] = [];
    transport.subscribe((message) => seen.push(message.type));
    socket.simulateMessage({
      type: "event.batch",
      protocol_version: "v1",
      request_id: "e",
      scene_id: "s".repeat(36),
      sequence: 1,
      events: [],
    });
    expect(seen).toEqual(["event.batch"]);
  });

  it("resolves commands by idempotency key", async () => {
    const { transport, promise, socket } = connect();
    socket.simulateOpen();
    socket.simulateMessage(READY);
    await promise;

    const commandPromise = transport.submitCommand({
      command: "select_entity",
      sceneId: "s".repeat(36),
      entityId: "e".repeat(36),
    });
    const submitted = JSON.parse(socket.sent[1] as string) as CommandSubmit;
    expect(submitted.type).toBe("command.submit");
    socket.simulateMessage({
      type: "command.result",
      protocol_version: "v1",
      request_id: submitted.request_id,
      idempotency_key: submitted.idempotency_key,
      status: "completed",
      result: { accepted_by: "worldstate-backend" },
    });
    const result = await commandPromise;
    expect(result.status).toBe("completed");
  });

  it("sends binary frames only while open", async () => {
    const { transport, promise, socket } = connect();
    socket.simulateOpen();
    socket.simulateMessage(READY);
    await promise;
    const buffer = new ArrayBuffer(30);
    transport.sendFrame(buffer);
    expect(socket.sent).toHaveLength(2);
    socket.simulateServerClose("gone");
    transport.sendFrame(buffer);
    expect(socket.sent).toHaveLength(2);
  });

  it("notifies onClose for server-side drops but not client teardown", async () => {
    const first = connect();
    first.socket.simulateOpen();
    first.socket.simulateMessage(READY);
    await first.promise;
    const reasons: string[] = [];
    first.transport.onClose((reason) => reasons.push(reason));
    first.socket.simulateServerClose("backend restarted");
    expect(reasons).toEqual(["backend restarted"]);

    FakeWebSocket.instances = [];
    const second = connect();
    second.socket.simulateOpen();
    second.socket.simulateMessage(READY);
    await second.promise;
    const secondReasons: string[] = [];
    second.transport.onClose((reason) => secondReasons.push(reason));
    second.transport.close();
    expect(secondReasons).toEqual([]);
  });
});
