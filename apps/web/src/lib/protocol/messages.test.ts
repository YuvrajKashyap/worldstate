import { describe, expect, it } from "vitest";

import {
  makeCommand,
  makeHello,
  newIdempotencyKey,
  nextRequestId,
  parseServerMessage,
} from "./messages";

describe("parseServerMessage", () => {
  it("accepts every documented server type", () => {
    for (const type of [
      "server.ready",
      "frame.result",
      "world.patch",
      "event.batch",
      "command.result",
      "flow.slow_down",
      "error",
    ]) {
      const parsed = parseServerMessage(JSON.stringify({ type }));
      expect(parsed).not.toBeNull();
      expect(parsed?.type).toBe(type);
    }
  });

  it("rejects unknown types, non-objects, and invalid JSON", () => {
    expect(parseServerMessage(JSON.stringify({ type: "mystery" }))).toBeNull();
    expect(parseServerMessage(JSON.stringify({ no: "type" }))).toBeNull();
    expect(parseServerMessage("42")).toBeNull();
    expect(parseServerMessage("not json {")).toBeNull();
  });
});

describe("client message builders", () => {
  it("builds a protocol v1 hello with capabilities", () => {
    const hello = makeHello("a".repeat(36), ["cup"]);
    expect(hello.type).toBe("client.hello");
    expect(hello.protocol_version).toBe("v1");
    expect(hello.session_id).toHaveLength(36);
    expect(hello.prompts).toEqual(["cup"]);
    expect(hello.requested_capabilities).toContain("frame.result");
    expect(hello.request_id.length).toBeGreaterThan(0);
    expect(hello.request_id.length).toBeLessThanOrEqual(120);
  });

  it("omits empty prompts so the scene defaults apply", () => {
    const hello = makeHello("b".repeat(36));
    expect("prompts" in hello).toBe(false);
  });

  it("builds commands with valid idempotency keys", () => {
    const command = makeCommand({
      command: "select_entity",
      sceneId: "c".repeat(36),
      entityId: "d".repeat(36),
    });
    expect(command.type).toBe("command.submit");
    expect(command.idempotency_key.length).toBeGreaterThanOrEqual(16);
    expect(command.idempotency_key.length).toBeLessThanOrEqual(120);
    expect(command.entity_id).toBe("d".repeat(36));
    expect(command.expected_entity_state_id).toBeNull();
    expect(command.arguments).toEqual({});
  });

  it("generates unique request ids and idempotency keys", () => {
    expect(nextRequestId("x")).not.toBe(nextRequestId("x"));
    expect(newIdempotencyKey()).not.toBe(newIdempotencyKey());
  });
});
