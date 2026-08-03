/**
 * Deterministic client-side world simulation.
 *
 * Mirrors the backend's replay provider math and the Desk Change fixture
 * script (cup added/moved, book missing/rediscovered) so the full interface
 * can be exercised without the Python backend. Everything it emits is
 * labeled SIMULATION in the interface — it never masquerades as a backend.
 */

import type {
  EventKind,
  FrameObject,
  Presence,
  WorldEvent,
} from "../../protocol/messages";
import { objectCenter } from "../syntheticDesk";

export const MOCK_SCENE_ID = "01900000-0000-7000-8000-00000000s1m0";
export const MOCK_FRAME_WIDTH = 640;
export const MOCK_FRAME_HEIGHT = 360;
export const MOCK_FPS = 60;

type SimEntity = {
  id: string;
  label: string;
  index: number;
  presence: Presence;
  confidence: number;
  uncertainty: number;
  lastEventPosition: [number, number, number] | null;
  frozenPosition: [number, number, number] | null;
  frozenBox: [number, number, number, number] | null;
};

export type SimTick = {
  objects: FrameObject[];
  events: WorldEvent[];
};

function entityId(index: number): string {
  return `01900000-0000-7000-8000-0000000000e${String(index)}`;
}

function eventId(sequence: number, index: number, kind: string): string {
  const tail = `${String(sequence)}-${String(index)}-${kind}`
    .padStart(12, "0")
    .slice(-12);
  return `01900000-0000-7000-8000-${tail.replace(/[^a-z0-9]/gi, "0")}`;
}

function positionFor(
  index: number,
  sequence: number,
): [number, number, number] {
  const { x, y } = objectCenter(
    index,
    sequence,
    MOCK_FRAME_WIDTH,
    MOCK_FRAME_HEIGHT,
  );
  return [
    (x / MOCK_FRAME_WIDTH - 0.5) * 2.0,
    (0.5 - y / MOCK_FRAME_HEIGHT) * 1.2,
    1.0 + index * 0.25,
  ];
}

function boxFor(
  index: number,
  sequence: number,
): [number, number, number, number] {
  const { x, y } = objectCenter(
    index,
    sequence,
    MOCK_FRAME_WIDTH,
    MOCK_FRAME_HEIGHT,
  );
  const w = Math.max(32, MOCK_FRAME_WIDTH * (0.12 - index * 0.015));
  const h = Math.max(32, MOCK_FRAME_HEIGHT * (0.22 - index * 0.02));
  return [
    Math.max(0, x - w / 2),
    Math.max(0, y - h / 2),
    Math.min(MOCK_FRAME_WIDTH, x + w / 2),
    Math.min(MOCK_FRAME_HEIGHT, y + h / 2),
  ];
}

function distance(
  a: [number, number, number],
  b: [number, number, number],
): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

export class MockWorldEngine {
  private readonly entities: SimEntity[];
  private startedAtMs: number | null = null;
  private phoneRotationEmitted = false;

  constructor(labels: string[] = ["cup", "book", "phone"]) {
    this.entities = labels.slice(0, 3).map((label, index) => ({
      id: entityId(index),
      label,
      index,
      presence: "visible",
      confidence: Math.max(0.55, 0.94 - index * 0.08),
      uncertainty: 0.08 + index * 0.05,
      lastEventPosition: null,
      frozenPosition: null,
      frozenBox: null,
    }));
  }

  /** Advance the deterministic world using real capture time for its script. */
  tick(sequence: number, occurredAtIso: string): SimTick {
    const occurredAtMs = Date.parse(occurredAtIso);
    this.startedAtMs ??= occurredAtMs;
    const seconds = Math.max(0, (occurredAtMs - this.startedAtMs) / 1000);
    const events: WorldEvent[] = [];
    const objects: FrameObject[] = [];

    for (const entity of this.entities) {
      const isBook = entity.label === "book";
      const baseConfidence = Math.max(0.55, 0.94 - entity.index * 0.08);
      let presence: Presence = "visible";
      let kindEmitted: EventKind | null = null;

      if (isBook && seconds >= 12 && seconds < 18) {
        // Scripted disappearance: occluded -> missing with decay.
        presence = seconds < 13.5 ? "occluded" : "missing";
        if (entity.presence === "visible" && presence === "occluded") {
          kindEmitted = "occluded";
          entity.frozenPosition = positionFor(entity.index, sequence);
          entity.frozenBox = boxFor(entity.index, sequence);
        } else if (entity.presence === "occluded" && presence === "missing") {
          kindEmitted = "removed";
        }
        entity.confidence = Math.max(0.12, entity.confidence * 0.965);
        entity.uncertainty = Math.min(0.95, entity.uncertainty + 0.012);
      } else if (isBook && seconds >= 18 && entity.presence !== "visible") {
        presence = "rediscovered";
        kindEmitted = "rediscovered";
        entity.confidence = baseConfidence * 0.92;
        entity.uncertainty = 0.18;
        entity.frozenPosition = null;
        entity.frozenBox = null;
      } else {
        if (entity.presence === "rediscovered") {
          presence = "visible";
        }
        entity.confidence = Math.min(
          baseConfidence,
          entity.confidence + 0.015,
        );
        entity.uncertainty = Math.max(
          0.06 + entity.index * 0.04,
          entity.uncertainty - 0.01,
        );
      }

      const live = presence === "visible" || presence === "rediscovered";
      const position = live
        ? positionFor(entity.index, sequence)
        : (entity.frozenPosition ?? positionFor(entity.index, sequence));
      const box = live
        ? boxFor(entity.index, sequence)
        : (entity.frozenBox ?? boxFor(entity.index, sequence));

      if (sequence === 0) {
        kindEmitted = "added";
        entity.lastEventPosition = position;
      } else if (live && entity.lastEventPosition !== null) {
        if (distance(position, entity.lastEventPosition) > 0.22) {
          kindEmitted ??= "moved";
          entity.lastEventPosition = position;
        }
      }

      // One scripted rotation for the phone adds grammar variety.
      if (
        entity.label === "phone" &&
        seconds >= 3 &&
        !this.phoneRotationEmitted
      ) {
        kindEmitted = "rotated";
        this.phoneRotationEmitted = true;
      }

      if (kindEmitted !== null) {
        events.push({
          id: eventId(sequence, entity.index, kindEmitted),
          scene_id: MOCK_SCENE_ID,
          entity_id: entity.id,
          kind: kindEmitted,
          occurred_at: occurredAtIso,
          confidence: entity.confidence,
          evidence_ids: [eventId(sequence, entity.index, "ev")],
          payload: { simulated: true, position_m: position },
        });
      }

      entity.presence = presence;
      objects.push({
        entity_id: entity.id,
        label: entity.label,
        confidence: Number(entity.confidence.toFixed(4)),
        uncertainty: Number(entity.uncertainty.toFixed(4)),
        presence,
        box_xyxy: box,
        position_m: position,
        bounds_m: null,
        mask_artifact_id: null,
      });
    }

    return { objects, events };
  }
}
