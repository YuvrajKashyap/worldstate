import { beforeEach, describe, expect, it } from "vitest";

import {
  entityStateAt,
  ghostMarkers,
  useWorldStore,
} from "./worldStore";
import {
  PROTOCOL_VERSION,
  type FrameObject,
  type FrameResult,
  type WorldEvent,
} from "../lib/protocol/messages";

const T0 = 1_700_000_000_000;

function frameObject(overrides: Partial<FrameObject> = {}): FrameObject {
  return {
    entity_id: "e".repeat(36),
    label: "cup",
    confidence: 0.9,
    uncertainty: 0.1,
    presence: "visible",
    box_xyxy: [0, 0, 10, 10],
    position_m: [0.1, 0.2, 1.1],
    bounds_m: [0.2, 0.1, 0.15],
    mask_artifact_id: null,
    ...overrides,
  };
}

function frameResult(
  sequence: number,
  objects: FrameObject[],
  events: WorldEvent[] = [],
): FrameResult {
  return {
    type: "frame.result",
    protocol_version: PROTOCOL_VERSION,
    request_id: `frame-${String(sequence)}`,
    sequence,
    captured_at: new Date(T0 + sequence * 100).toISOString(),
    presented_at: new Date(T0 + sequence * 100 + 40).toISOString(),
    objects,
    events,
    metrics: {
      sequence,
      capture_to_result_ms: 40,
      inference_ms: 10,
      queue_depth: 0,
      dropped_frames: 2,
      discovery_ran: false,
      depth_ran: false,
      embedding_ran: false,
    },
    quality: { sharpness: 0.5 },
  };
}

function worldEvent(overrides: Partial<WorldEvent> = {}): WorldEvent {
  return {
    id: "f".repeat(36),
    scene_id: "s".repeat(36),
    entity_id: "e".repeat(36),
    kind: "moved",
    occurred_at: new Date(T0 + 500).toISOString(),
    confidence: 0.8,
    evidence_ids: ["v".repeat(36)],
    payload: {},
    ...overrides,
  };
}

describe("worldStore", () => {
  beforeEach(() => {
    useWorldStore.getState().reset();
  });

  it("creates entity records with history on first sight", () => {
    useWorldStore.getState().ingestFrameResult(frameResult(0, [frameObject()]));
    const state = useWorldStore.getState();
    const record = state.entities["e".repeat(36)];
    expect(state.order).toEqual(["e".repeat(36)]);
    expect(record?.label).toBe("cup");
    expect(record?.history).toHaveLength(1);
    expect(record?.lastVisibleAt).toBe(T0);
    expect(state.telemetry.frameCount).toBe(1);
    expect(state.telemetry.droppedFrames).toBe(2);
  });

  it("prefers browser-local capture latency over the server wall-clock field", () => {
    useWorldStore
      .getState()
      .ingestFrameResult(frameResult(0, [frameObject()]), 27.25, 6.5, 0.25);

    const telemetry = useWorldStore.getState().telemetry;
    expect(telemetry.latencyMs).toEqual([27.25]);
    expect(telemetry.encodeMs).toEqual([6.5]);
    expect(telemetry.resultToCaptureMs).toEqual([0.25]);
    expect(telemetry.lastMetrics?.capture_to_result_ms).toBe(27.25);
  });

  it("can count learned results without rebuilding the presented scene", () => {
    const frame = frameResult(0, [frameObject()]);
    useWorldStore.getState().noteFrameResult(frame, 31, 2, 10);

    expect(useWorldStore.getState().telemetry.frameCount).toBe(10);
    expect(useWorldStore.getState().order).toEqual([]);

    useWorldStore.getState().presentFrame(frame);
    expect(useWorldStore.getState().order).toEqual(["e".repeat(36)]);
  });

  it("aggregates every telemetry sample in a presentation batch", () => {
    const store = useWorldStore.getState();
    store.noteFrameBatch(
      frameResult(0, []),
      [30, 40, 50],
      [1, 2, 3],
      3,
      [0, 0.1, 0.2],
      [8, 9, 10],
    );

    let telemetry = useWorldStore.getState().telemetry;
    expect(telemetry.latencyMs).toEqual([30, 40, 50]);
    expect(telemetry.encodeMs).toEqual([1, 2, 3]);
    expect(telemetry.resultToCaptureMs).toEqual([0, 0.1, 0.2]);
    expect(telemetry.inferenceMs).toEqual([8, 9, 10]);
    expect(telemetry.frameCount).toBe(3);
    expect(telemetry.lastMetrics?.capture_to_result_ms).toBe(50);

    store.noteFrameBatch(frameResult(10, []), [], [], 3, [], []);
    telemetry = useWorldStore.getState().telemetry;
    expect(telemetry.latencyMs).toEqual([30, 40, 50]);
    expect(telemetry.encodeMs).toEqual([1, 2, 3]);
    expect(telemetry.frameCount).toBe(3);
    expect(telemetry.updatesPerSecond).toBeGreaterThan(0);
    expect(telemetry.lastMetrics?.capture_to_result_ms).toBe(40);
  });

  it("bounds complete telemetry batches to the rolling sample limit", () => {
    const samples = Array.from({ length: 140 }, (_value, index) => index);
    useWorldStore.getState().noteFrameBatch(
      frameResult(20, []),
      samples,
      samples,
      140,
      samples,
      samples,
    );

    const telemetry = useWorldStore.getState().telemetry;
    expect(telemetry.latencyMs).toHaveLength(120);
    expect(telemetry.latencyMs[0]).toBe(20);
    expect(telemetry.latencyMs.at(-1)).toBe(139);
  });

  it("appends history and tracks visibility transitions", () => {
    const store = useWorldStore.getState();
    store.ingestFrameResult(frameResult(0, [frameObject()]));
    store.ingestFrameResult(
      frameResult(1, [
        frameObject({ presence: "occluded", position_m: [0.3, 0.2, 1.1] }),
      ]),
    );
    const record = useWorldStore.getState().entities["e".repeat(36)];
    expect(record?.history).toHaveLength(2);
    expect(record?.presence).toBe("occluded");
    // Last visible stays at the first frame's time.
    expect(record?.lastVisibleAt).toBe(T0);
  });

  it("looks up historical state with entityStateAt", () => {
    const store = useWorldStore.getState();
    for (let sequence = 0; sequence < 5; sequence += 1) {
      store.ingestFrameResult(
        frameResult(sequence, [
          frameObject({ confidence: 0.5 + sequence * 0.1 }),
        ]),
      );
    }
    const record = useWorldStore.getState().entities["e".repeat(36)];
    if (record === undefined) {
      throw new Error("record missing");
    }
    expect(entityStateAt(record, T0 - 1)).toBeNull();
    expect(entityStateAt(record, T0)?.confidence).toBeCloseTo(0.5);
    expect(entityStateAt(record, T0 + 250)?.confidence).toBeCloseTo(0.7);
    expect(entityStateAt(record, T0 + 10_000)?.confidence).toBeCloseTo(0.9);
  });

  it("deduplicates events and produces pulses and announcements", () => {
    const store = useWorldStore.getState();
    store.ingestFrameResult(frameResult(0, [frameObject()]));
    const event = worldEvent();
    store.ingestEvents("scene", [event]);
    store.ingestEvents("scene", [event]);
    const state = useWorldStore.getState();
    expect(state.events).toHaveLength(1);
    expect(state.pulses).toHaveLength(1);
    expect(state.announcement).toBe("cup moved.");
    expect(state.entities["e".repeat(36)]?.eventCount).toBe(1);
  });

  it("derives ghost markers from change events", () => {
    const store = useWorldStore.getState();
    store.ingestFrameResult(frameResult(0, [frameObject()]));
    store.ingestFrameResult(
      frameResult(1, [frameObject({ position_m: [0.6, 0.2, 1.1] })]),
    );
    store.ingestEvents("scene", [
      worldEvent({ occurred_at: new Date(T0 + 100).toISOString() }),
    ]);
    const state = useWorldStore.getState();
    const ghosts = ghostMarkers(state.entities, state.events);
    expect(ghosts).toHaveLength(1);
    expect(ghosts[0]?.kind).toBe("moved");
    expect(ghosts[0]?.position).toEqual([0.1, 0.2, 1.1]);
  });

  it("ignores non-change events for ghosts", () => {
    const store = useWorldStore.getState();
    store.ingestFrameResult(frameResult(0, [frameObject()]));
    store.ingestEvents("scene", [
      worldEvent({ kind: "occluded", id: "1".repeat(36) }),
      worldEvent({ kind: "confidence_changed", id: "2".repeat(36) }),
    ]);
    const state = useWorldStore.getState();
    expect(ghostMarkers(state.entities, state.events)).toHaveLength(0);
  });

  it("resets cleanly", () => {
    const store = useWorldStore.getState();
    store.ingestFrameResult(frameResult(0, [frameObject()]));
    store.reset();
    const state = useWorldStore.getState();
    expect(state.order).toHaveLength(0);
    expect(state.events).toHaveLength(0);
    expect(state.timeOrigin).toBeNull();
  });
});
