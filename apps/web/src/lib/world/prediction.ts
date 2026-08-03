import type { Presence } from "../protocol/messages";

export type Box = [number, number, number, number];
export type Position = [number, number, number];

export type MotionSample = {
  at: number;
  presence: Presence;
  box: Box;
  position: Position | null;
};

export type MotionEstimate = {
  observedAt: number;
  boxVelocity: Box | null;
  positionVelocity: Position | null;
};

const HISTORY_WINDOW_MS = 420;
const MAX_SAMPLES = 8;
const MIN_SPAN_MS = 25;
const MAX_BOX_SPEED_PX_PER_MS = 1.5;
const MAX_POSITION_SPEED_M_PER_MS = 0.008;
export const MAX_PREDICTION_HORIZON_MS = 120;

function isObserved(presence: Presence): boolean {
  return presence === "visible" || presence === "rediscovered";
}
function clamp(value: number, limit: number): number {
  return Math.max(-limit, Math.min(limit, value));
}

function recentObserved(samples: MotionSample[]): MotionSample[] {
  const newest = samples.at(-1);
  if (newest === undefined || !isObserved(newest.presence)) {
    return [];
  }
  const cutoff = newest.at - HISTORY_WINDOW_MS;
  return samples
    .filter((sample) => sample.at >= cutoff && isObserved(sample.presence))
    .slice(-MAX_SAMPLES);
}

/** Least-squares velocity in value-units per millisecond. */
function regressVelocity(
  samples: MotionSample[],
  dimensions: number,
  select: (sample: MotionSample) => readonly number[] | null,
  speedLimit: number,
): number[] | null {
  const usable = samples.flatMap((sample) => {
    const value = select(sample);
    return value === null ? [] : [{ at: sample.at, value }];
  });
  const first = usable.at(0);
  const last = usable.at(-1);
  if (
    usable.length < 2 ||
    first === undefined ||
    last === undefined ||
    last.at - first.at < MIN_SPAN_MS
  ) {
    return null;
  }

  const meanAt = usable.reduce((sum, sample) => sum + sample.at, 0) / usable.length;
  const denominator = usable.reduce(
    (sum, sample) => sum + (sample.at - meanAt) ** 2,
    0,
  );
  if (denominator <= 0) {
    return null;
  }

  return Array.from({ length: dimensions }, (_, dimension) => {
    const meanValue =
      usable.reduce((sum, sample) => sum + (sample.value[dimension] ?? 0), 0) /
      usable.length;
    const numerator = usable.reduce(
      (sum, sample) =>
        sum +
        (sample.at - meanAt) *
          ((sample.value[dimension] ?? meanValue) - meanValue),
      0,
    );
    return clamp(numerator / denominator, speedLimit);
  });
}

export function estimateMotion(samples: MotionSample[]): MotionEstimate | null {
  const recent = recentObserved(samples);
  const newest = recent.at(-1);
  if (newest === undefined) {
    return null;
  }
  const boxVelocity = regressVelocity(
    recent,
    4,
    (sample) => sample.box,
    MAX_BOX_SPEED_PX_PER_MS,
  );
  const positionVelocity = regressVelocity(
    recent,
    3,
    (sample) => sample.position,
    MAX_POSITION_SPEED_M_PER_MS,
  );
  return {
    observedAt: newest.at,
    boxVelocity: boxVelocity as Box | null,
    positionVelocity: positionVelocity as Position | null,
  };
}

function horizon(observedAt: number, now: number, maxHorizonMs: number): number {
  return Math.max(0, Math.min(maxHorizonMs, now - observedAt));
}

export function projectBox(
  box: Box,
  velocity: Box | null,
  observedAt: number,
  now: number,
  maxHorizonMs = MAX_PREDICTION_HORIZON_MS,
): Box {
  if (velocity === null) {
    return box;
  }
  const ahead = horizon(observedAt, now, maxHorizonMs);
  return box.map((value, index) => value + (velocity[index] ?? 0) * ahead) as Box;
}

export function projectPosition(
  position: Position,
  velocity: Position | null,
  observedAt: number,
  now: number,
  maxHorizonMs = MAX_PREDICTION_HORIZON_MS,
): Position {
  if (velocity === null) {
    return position;
  }
  const ahead = horizon(observedAt, now, maxHorizonMs);
  return position.map(
    (value, index) => value + (velocity[index] ?? 0) * ahead,
  ) as Position;
}
