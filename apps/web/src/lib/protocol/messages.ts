/**
 * WorldState live protocol v1 message types.
 *
 * Mirrors packages/contracts/protocol-v1.schema.json exactly. The wire format
 * is a strict discriminated union on `type`; unknown message types are
 * surfaced to callers as `null` so transport layers can fail loudly.
 */

export const PROTOCOL_VERSION = "v1" as const;

export type Presence =
  | "visible"
  | "occluded"
  | "predicted"
  | "missing"
  | "rediscovered"
  | "archived";

export type EventKind =
  | "added"
  | "moved"
  | "rotated"
  | "removed"
  | "occluded"
  | "rediscovered"
  | "confidence_changed";

export type CommandName =
  | "select_entity"
  | "pin_entity"
  | "set_entity_visibility"
  | "set_timeline_time"
  | "query_entity"
  | "find_last_seen"
  | "start_scan"
  | "cancel_job";

export type ClientHello = {
  type: "client.hello";
  protocol_version: typeof PROTOCOL_VERSION;
  request_id: string;
  session_id: string;
  prompts?: string[];
  requested_capabilities?: string[];
};

export type CommandSubmit = {
  type: "command.submit";
  protocol_version: typeof PROTOCOL_VERSION;
  request_id: string;
  idempotency_key: string;
  command: CommandName;
  scene_id: string;
  entity_id?: string | null;
  expected_entity_state_id?: string | null;
  arguments?: Record<string, unknown>;
};

export type ClientMessage = ClientHello | CommandSubmit;

export type SystemLimits = {
  max_frame_bytes: number;
  max_frame_width: number;
  max_frame_height: number;
  max_upload_bytes: number;
  max_video_duration_seconds: number;
  max_pending_jobs: number;
  storage_quota_bytes: number;
};

export type ProviderMode = "replay" | "classical" | "models";

export type ServerReady = {
  type: "server.ready";
  protocol_version: typeof PROTOCOL_VERSION;
  request_id: string;
  accepted_capabilities: string[];
  provider_mode: ProviderMode;
  limits: SystemLimits;
};

export type FrameObject = {
  entity_id: string;
  label: string;
  confidence: number;
  uncertainty: number;
  presence: Presence;
  box_xyxy: [number, number, number, number];
  position_m: [number, number, number] | null;
  bounds_m: [number, number, number] | null;
  mask_artifact_id?: string | null;
};

export type WorldEvent = {
  id: string;
  scene_id: string;
  entity_id: string;
  kind: EventKind;
  occurred_at: string;
  confidence: number;
  evidence_ids: string[];
  payload: Record<string, unknown>;
};

export type FrameMetrics = {
  sequence: number;
  capture_to_result_ms: number;
  inference_ms: number;
  queue_depth: 0 | 1;
  dropped_frames: number;
  discovery_ran: boolean;
  depth_ran: boolean;
  embedding_ran: boolean;
};

export type FrameResult = {
  type: "frame.result";
  protocol_version: typeof PROTOCOL_VERSION;
  request_id: string;
  sequence: number;
  captured_at: string;
  presented_at: string;
  objects: FrameObject[];
  events: WorldEvent[];
  metrics: FrameMetrics;
  quality: Record<string, number>;
};

export type WorldPatch = {
  type: "world.patch";
  protocol_version: typeof PROTOCOL_VERSION;
  request_id: string;
  scene_id: string;
  sequence: number;
  entities: FrameObject[];
};

export type EventBatch = {
  type: "event.batch";
  protocol_version: typeof PROTOCOL_VERSION;
  request_id: string;
  scene_id: string;
  sequence: number;
  events: WorldEvent[];
};

export type CommandResult = {
  type: "command.result";
  protocol_version: typeof PROTOCOL_VERSION;
  request_id: string;
  idempotency_key: string;
  status: "accepted" | "completed" | "rejected";
  result?: Record<string, unknown>;
};

export type FlowSlowDown = {
  type: "flow.slow_down";
  protocol_version: typeof PROTOCOL_VERSION;
  request_id: string;
  retry_after_ms: number;
  reason: "busy" | "live_session_active" | "resource_limit";
};

export type WebSocketError = {
  type: "error";
  protocol_version: typeof PROTOCOL_VERSION;
  request_id: string | null;
  code: string;
  message: string;
  recoverable: boolean;
};

export type ServerMessage =
  | ServerReady
  | FrameResult
  | WorldPatch
  | EventBatch
  | CommandResult
  | FlowSlowDown
  | WebSocketError;

const SERVER_TYPES = new Set<ServerMessage["type"]>([
  "server.ready",
  "frame.result",
  "world.patch",
  "event.batch",
  "command.result",
  "flow.slow_down",
  "error",
]);

/** Parse a text frame from the server; returns null for unknown payloads. */
export function parseServerMessage(raw: string): ServerMessage | null {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (
    typeof value !== "object" ||
    value === null ||
    typeof (value as { type?: unknown }).type !== "string"
  ) {
    return null;
  }
  const type = (value as { type: string }).type;
  if (!SERVER_TYPES.has(type as ServerMessage["type"])) {
    return null;
  }
  return value as ServerMessage;
}

let requestCounter = 0;

export function nextRequestId(prefix: string): string {
  requestCounter += 1;
  return `${prefix}-${String(Date.now())}-${String(requestCounter)}`;
}

/** Idempotency keys must be 16–120 characters. */
export function newIdempotencyKey(): string {
  const random =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${String(Date.now())}-${String(Math.random()).slice(2)}`;
  return `ws-cmd-${random}`;
}

export function makeHello(sessionId: string, prompts?: string[]): ClientHello {
  return {
    type: "client.hello",
    protocol_version: PROTOCOL_VERSION,
    request_id: nextRequestId("hello"),
    session_id: sessionId,
    ...(prompts && prompts.length > 0 ? { prompts } : {}),
    requested_capabilities: [
      "frame.result",
      "command.submit",
    ],
  };
}

export type CommandInput = {
  command: CommandName;
  sceneId: string;
  entityId?: string;
  expectedEntityStateId?: string;
  arguments?: Record<string, unknown>;
};

export function makeCommand(input: CommandInput): CommandSubmit {
  return {
    type: "command.submit",
    protocol_version: PROTOCOL_VERSION,
    request_id: nextRequestId("cmd"),
    idempotency_key: newIdempotencyKey(),
    command: input.command,
    scene_id: input.sceneId,
    entity_id: input.entityId ?? null,
    expected_entity_state_id: input.expectedEntityStateId ?? null,
    arguments: input.arguments ?? {},
  };
}
