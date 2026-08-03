/**
 * Active Scan Coach.
 *
 * Heuristic guidance derived from live capture-quality metrics and entity
 * uncertainty. It is presented as guidance, never as a measured guarantee:
 * these are explainable rules over the quality signals the backend already
 * reports (sharpness, exposure, contrast, keyframe score) plus memory state.
 */

import type { EntityRecord } from "../../state/worldStore";

export type CoachDirective = {
  id: string;
  icon: "steady" | "light" | "parallax" | "revisit" | "closer" | "done";
  headline: string;
  detail: string;
  severity: "act" | "suggest" | "settle";
};

export type CoachInput = {
  quality: Record<string, number>;
  entities: Record<string, EntityRecord>;
  order: string[];
  updatesPerSecond: number;
  nowMs: number;
};

const STALE_AFTER_MS = 6_000;

export function adviseCoach(input: CoachInput): CoachDirective[] {
  const directives: CoachDirective[] = [];
  const sharpness = input.quality.sharpness ?? 1;
  const exposure = input.quality.exposure ?? 1;
  const brightness = input.quality.brightness ?? 0.5;
  const keyframe = input.quality.keyframe_score ?? 1;

  if (sharpness < 0.28) {
    directives.push({
      id: "hold-still",
      icon: "steady",
      headline: "Hold still",
      detail: "Motion blur is high; steady the camera for a sharper keyframe.",
      severity: "act",
    });
  }
  if (exposure < 0.6 || brightness < 0.18) {
    directives.push({
      id: "add-light",
      icon: "light",
      headline: "Add light",
      detail: "The frame is under-exposed; brighten the scene or open blinds.",
      severity: "act",
    });
  } else if (brightness > 0.88) {
    directives.push({
      id: "cut-glare",
      icon: "light",
      headline: "Reduce glare",
      detail: "Highlights are clipping; angle the camera away from the light.",
      severity: "suggest",
    });
  }

  const uncertain: EntityRecord[] = [];
  const stale: EntityRecord[] = [];
  for (const id of input.order) {
    const record = input.entities[id];
    if (record === undefined) {
      continue;
    }
    if (record.uncertainty > 0.5 && record.presence !== "missing") {
      uncertain.push(record);
    }
    if (
      record.lastVisibleAt !== null &&
      input.nowMs - record.lastVisibleAt > STALE_AFTER_MS &&
      record.presence !== "archived"
    ) {
      stale.push(record);
    }
  }

  const target = stale[0] ?? uncertain[0];
  if (target !== undefined) {
    const isStale = stale.length > 0;
    directives.push({
      id: `revisit-${target.id}`,
      icon: "revisit",
      headline: `Revisit the ${target.label}`,
      detail: isStale
        ? `The ${target.label} has not been observed recently; sweep its last position.`
        : `Uncertainty on the ${target.label} is high; a closer or side view would help.`,
      severity: "suggest",
    });
  }

  if (directives.length === 0 && keyframe > 0.55) {
    if (input.updatesPerSecond > 4) {
      directives.push({
        id: "parallax",
        icon: "parallax",
        headline: "Drift slowly left or right",
        detail: "Coverage is good; slow parallax adds depth evidence.",
        severity: "settle",
      });
    } else {
      directives.push({
        id: "coverage-ok",
        icon: "done",
        headline: "Coverage is stable",
        detail: "Marginal information gain is low; you can stop scanning.",
        severity: "settle",
      });
    }
  }

  return directives.slice(0, 2);
}
