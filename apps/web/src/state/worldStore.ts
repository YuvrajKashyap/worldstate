/**
 * Client world memory.
 *
 * Ingests live protocol messages into per-entity temporal histories
 * (append-only rings), an event log, change pulses, and rolling telemetry.
 * The Time Scrubber, Ghost Mode, and X-ray Memory all read from here;
 * scrubbing never mutates live state (HOL-005) — historical views are pure
 * lookups over the recorded rings.
 */

import { create } from "zustand";

import type {
  EventKind,
  FrameMetrics,
  FrameObject,
  FrameResult,
  Presence,
  WorldEvent,
} from "../lib/protocol/messages";

export type EntitySnapshot = {
  at: number;
  presence: Presence;
  confidence: number;
  uncertainty: number;
  position: [number, number, number] | null;
  bounds: [number, number, number] | null;
  box: [number, number, number, number];
};

export type EntityRecord = {
  id: string;
  label: string;
  firstSeenAt: number;
  lastSeenAt: number;
  lastVisibleAt: number | null;
  presence: Presence;
  confidence: number;
  uncertainty: number;
  position: [number, number, number] | null;
  bounds: [number, number, number] | null;
  box: [number, number, number, number];
  history: EntitySnapshot[];
  eventCount: number;
};

export type Pulse = {
  id: string;
  entityId: string;
  kind: EventKind;
  at: number;
  position: [number, number, number] | null;
};

export type Telemetry = {
  latencyMs: number[];
  encodeMs: number[];
  resultToCaptureMs: number[];
  inferenceMs: number[];
  droppedFrames: number;
  skippedIntervals: number;
  updatesPerSecond: number;
  frameCount: number;
  lastQuality: Record<string, number>;
  lastMetrics: FrameMetrics | null;
};

const HISTORY_LIMIT = 900;
const EVENT_LIMIT = 400;
const PULSE_LIMIT = 24;
const LATENCY_RING = 120;

export type WorldState = {
  sceneId: string | null;
  entities: Record<string, EntityRecord>;
  order: string[];
  events: WorldEvent[];
  pulses: Pulse[];
  telemetry: Telemetry;
  timeOrigin: number | null;
  lastFrameAt: number | null;
  announcement: string | null;
  ingestFrameResult: (
    frame: FrameResult,
    captureToResultMs?: number,
    encodeMs?: number,
    resultToCaptureMs?: number,
  ) => void;
  noteFrameResult: (
    frame: FrameResult,
    captureToResultMs?: number,
    encodeMs?: number,
    receivedCount?: number,
    resultToCaptureMs?: number,
  ) => void;
  noteFrameBatch: (
    frame: FrameResult,
    captureToResultMs: number[],
    encodeMs: number[],
    receivedCount: number,
    resultToCaptureMs: number[],
    inferenceMs: number[],
  ) => void;
  presentFrame: (frame: FrameResult) => void;
  ingestEvents: (sceneId: string, events: WorldEvent[]) => void;
  noteSkippedIntervals: (count: number) => void;
  reset: () => void;
};

function emptyTelemetry(): Telemetry {
  return {
    latencyMs: [],
    encodeMs: [],
    resultToCaptureMs: [],
    inferenceMs: [],
    droppedFrames: 0,
    skippedIntervals: 0,
    updatesPerSecond: 0,
    frameCount: 0,
    lastQuality: {},
    lastMetrics: null,
  };
}

function pushRing<T>(ring: T[], value: T, limit: number): T[] {
  const next = ring.length >= limit ? ring.slice(ring.length - limit + 1) : ring.slice();
  next.push(value);
  return next;
}

function pushRingBatch<T>(ring: T[], values: T[], limit: number): T[] {
  if (values.length === 0) {
    return ring;
  }
  return [...ring, ...values].slice(-limit);
}

function snapshotOf(object: FrameObject, at: number): EntitySnapshot {
  return {
    at,
    presence: object.presence,
    confidence: object.confidence,
    uncertainty: object.uncertainty,
    position: object.position_m,
    bounds: object.bounds_m,
    box: object.box_xyxy,
  };
}

function announcementFor(event: WorldEvent, label: string): string {
  switch (event.kind) {
    case "added":
      return `${label} entered the scene.`;
    case "moved":
      return `${label} moved.`;
    case "rotated":
      return `${label} rotated.`;
    case "removed":
      return `${label} is missing from its expected location.`;
    case "occluded":
      return `${label} is occluded.`;
    case "rediscovered":
      return `${label} was rediscovered.`;
    case "confidence_changed":
      return `${label} confidence updated.`;
  }
}

export const useWorldStore = create<WorldState>((set, get) => ({
  sceneId: null,
  entities: {},
  order: [],
  events: [],
  pulses: [],
  telemetry: emptyTelemetry(),
  timeOrigin: null,
  lastFrameAt: null,
  announcement: null,

  ingestFrameResult(frame, captureToResultMs, encodeMs, resultToCaptureMs) {
    get().noteFrameResult(
      frame,
      captureToResultMs,
      encodeMs,
      undefined,
      resultToCaptureMs,
    );
    get().presentFrame(frame);
  },

  noteFrameResult(
    frame,
    captureToResultMs,
    encodeMs,
    receivedCount,
    resultToCaptureMs,
  ) {
    get().noteFrameBatch(
      frame,
      [captureToResultMs ?? frame.metrics.capture_to_result_ms],
      encodeMs === undefined ? [] : [encodeMs],
      receivedCount ?? get().telemetry.frameCount + 1,
      resultToCaptureMs === undefined ? [] : [resultToCaptureMs],
      [frame.metrics.inference_ms],
    );
  },

  noteFrameBatch(
    frame,
    captureToResultMs,
    encodeMs,
    receivedCount,
    resultToCaptureMs,
    inferenceMs,
  ) {
    const at = Date.parse(frame.captured_at);
    const effectiveMetrics: FrameMetrics = {
      ...frame.metrics,
      capture_to_result_ms:
        captureToResultMs.at(-1) ?? frame.metrics.capture_to_result_ms,
    };
    set((state) => {
      const previousCount = state.telemetry.frameCount;
      const observedCount = Math.max(previousCount + captureToResultMs.length, receivedCount);
      const elapsed =
        state.timeOrigin !== null && at > state.timeOrigin
          ? (at - state.timeOrigin) / 1000
          : 0;
      const telemetry: Telemetry = {
        latencyMs: pushRingBatch(
          state.telemetry.latencyMs,
          captureToResultMs,
          LATENCY_RING,
        ),
        encodeMs: pushRingBatch(state.telemetry.encodeMs, encodeMs, LATENCY_RING),
        resultToCaptureMs: pushRingBatch(
          state.telemetry.resultToCaptureMs,
          resultToCaptureMs,
          LATENCY_RING,
        ),
        inferenceMs: pushRingBatch(
          state.telemetry.inferenceMs,
          inferenceMs,
          LATENCY_RING,
        ),
        droppedFrames: frame.metrics.dropped_frames,
        skippedIntervals: state.telemetry.skippedIntervals,
        updatesPerSecond:
          elapsed > 0.5 ? observedCount / elapsed : state.telemetry.updatesPerSecond,
        frameCount: observedCount,
        lastQuality: frame.quality,
        lastMetrics: effectiveMetrics,
      };

      return {
        telemetry,
        timeOrigin: state.timeOrigin ?? at,
      };
    });
    if (frame.events.length > 0) {
      get().ingestEvents(frame.events[0]?.scene_id ?? "", frame.events);
    }
  },

  presentFrame(frame) {
    const at = Date.parse(frame.captured_at);
    set((state) => {
      const entities = { ...state.entities };
      const order = [...state.order];
      for (const object of frame.objects) {
        const existing = entities[object.entity_id];
        const visible =
          object.presence === "visible" || object.presence === "rediscovered";
        if (existing === undefined) {
          entities[object.entity_id] = {
            id: object.entity_id,
            label: object.label,
            firstSeenAt: at,
            lastSeenAt: at,
            lastVisibleAt: visible ? at : null,
            presence: object.presence,
            confidence: object.confidence,
            uncertainty: object.uncertainty,
            position: object.position_m,
            bounds: object.bounds_m,
            box: object.box_xyxy,
            history: [snapshotOf(object, at)],
            eventCount: 0,
          };
          order.push(object.entity_id);
        } else {
          entities[object.entity_id] = {
            ...existing,
            label: object.label,
            lastSeenAt: at,
            lastVisibleAt: visible ? at : existing.lastVisibleAt,
            presence: object.presence,
            confidence: object.confidence,
            uncertainty: object.uncertainty,
            position: object.position_m,
            bounds: object.bounds_m,
            box: object.box_xyxy,
            history: pushRing(existing.history, snapshotOf(object, at), HISTORY_LIMIT),
          };
        }
      }
      return { entities, order, lastFrameAt: at };
    });
  },

  ingestEvents(sceneId, incoming) {
    if (incoming.length === 0) {
      return;
    }
    set((state) => {
      const known = new Set(state.events.map((event) => event.id));
      const fresh = incoming.filter((event) => !known.has(event.id));
      if (fresh.length === 0) {
        return {};
      }
      let events = state.events;
      let pulses = state.pulses;
      const entities = { ...state.entities };
      let announcement = state.announcement;
      for (const event of fresh) {
        events = pushRing(events, event, EVENT_LIMIT);
        const record = entities[event.entity_id];
        const position =
          (Array.isArray(event.payload.position_m)
            ? (event.payload.position_m as [number, number, number])
            : null) ??
          record?.position ??
          null;
        pulses = pushRing(
          pulses,
          {
            id: event.id,
            entityId: event.entity_id,
            kind: event.kind,
            at: Date.parse(event.occurred_at),
            position,
          },
          PULSE_LIMIT,
        );
        if (record !== undefined) {
          entities[event.entity_id] = {
            ...record,
            eventCount: record.eventCount + 1,
          };
          announcement = announcementFor(event, record.label);
        }
      }
      return {
        sceneId: state.sceneId ?? sceneId,
        events,
        pulses,
        entities,
        announcement,
      };
    });
  },

  noteSkippedIntervals(count) {
    set((state) => ({
      telemetry: { ...state.telemetry, skippedIntervals: count },
    }));
  },

  reset() {
    set({
      sceneId: null,
      entities: {},
      order: [],
      events: [],
      pulses: [],
      telemetry: emptyTelemetry(),
      timeOrigin: null,
      lastFrameAt: null,
      announcement: null,
    });
  },
}));

/** Binary-search the newest snapshot at or before `atMs`. */
export function entityStateAt(
  record: EntityRecord,
  atMs: number,
): EntitySnapshot | null {
  const { history } = record;
  if (history.length === 0) {
    return null;
  }
  const first = history[0];
  if (first === undefined || atMs < first.at) {
    return null;
  }
  let low = 0;
  let high = history.length - 1;
  while (low < high) {
    const mid = Math.ceil((low + high) / 2);
    const sample = history[mid];
    if (sample !== undefined && sample.at <= atMs) {
      low = mid;
    } else {
      high = mid - 1;
    }
  }
  return history[low] ?? null;
}

export type GhostMarker = {
  key: string;
  entityId: string;
  label: string;
  kind: EventKind;
  at: number;
  position: [number, number, number];
};

/**
 * Ghost Mode: previous positions at the moments change events occurred.
 * Each ghost carries its event type, timestamp, and the confidence the
 * entity had at that time.
 */
export function ghostMarkers(
  entities: Record<string, EntityRecord>,
  events: WorldEvent[],
  limitPerEntity = 4,
): GhostMarker[] {
  const ghosts: GhostMarker[] = [];
  const perEntity = new Map<string, number>();
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event === undefined) {
      continue;
    }
    if (
      event.kind !== "moved" &&
      event.kind !== "removed" &&
      event.kind !== "rediscovered" &&
      event.kind !== "rotated"
    ) {
      continue;
    }
    const used = perEntity.get(event.entity_id) ?? 0;
    if (used >= limitPerEntity) {
      continue;
    }
    const record = entities[event.entity_id];
    if (record === undefined) {
      continue;
    }
    const at = Date.parse(event.occurred_at);
    // The state just before the event is the ghost's location.
    const before = entityStateAt(record, at - 1) ?? entityStateAt(record, at);
    const position =
      (Array.isArray(event.payload.position_m)
        ? (event.payload.position_m as [number, number, number])
        : null) ?? before?.position;
    if (position === undefined || position === null) {
      continue;
    }
    perEntity.set(event.entity_id, used + 1);
    ghosts.push({
      key: event.id,
      entityId: event.entity_id,
      label: record.label,
      kind: event.kind,
      at,
      position,
    });
  }
  return ghosts;
}
