/**
 * Gesture recognition over smoothed hand landmarks (HOL-002).
 *
 * Pure geometric features + hysteresis state. Recognition is separate from
 * interaction: this module reports *what the hands are doing*; the machine
 * and overlay decide *what that means* in the current mode.
 */

import {
  HandSmoother,
  INDEX_MCP,
  INDEX_PIP,
  INDEX_TIP,
  MIDDLE_MCP,
  MIDDLE_TIP,
  PINKY_TIP,
  RING_TIP,
  THUMB_TIP,
  WRIST,
  type RawHand,
  type Vec2,
} from "./landmarks";

export type HandGesture = {
  handedness: "Left" | "Right";
  score: number;
  center: Vec2;
  velocity: Vec2;
  /** 0 = fully pinched, larger = open; normalized by hand scale. */
  pinchRatio: number;
  pinched: boolean;
  /** 0..1 fraction of extended fingers. */
  openness: number;
  palmOpen: boolean;
  pointing: boolean;
  pointerTip: Vec2;
  landmarks: Vec2[];
};

export type TwoHandGesture = {
  span: number;
  angleRad: number;
  center: Vec2;
};

export type GestureFrame = {
  hands: HandGesture[];
  twoHand: TwoHandGesture | null;
  bothPalmsOpen: boolean;
  timestampMs: number;
};

const PINCH_ENGAGE = 0.34;
const PINCH_RELEASE = 0.46;
const PALM_OPEN_ENGAGE = 0.78;
const PALM_OPEN_RELEASE = 0.6;
const MIN_SCORE = 0.55;

function dist(a: Vec2, b: Vec2): number {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function handScale(landmarks: Vec2[]): number {
  const wrist = landmarks[WRIST];
  const middleMcp = landmarks[MIDDLE_MCP];
  if (wrist === undefined || middleMcp === undefined) {
    return 0.1;
  }
  return Math.max(0.02, dist(wrist, middleMcp));
}

function fingerExtension(landmarks: Vec2[], tip: number): number {
  const wrist = landmarks[WRIST];
  const tipPoint = landmarks[tip];
  if (wrist === undefined || tipPoint === undefined) {
    return 0;
  }
  return dist(wrist, tipPoint) / handScale(landmarks);
}

/** Fraction of the four fingers that are extended past their knuckles. */
export function opennessOf(landmarks: Vec2[]): number {
  const tips = [INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP];
  let extended = 0;
  for (const tip of tips) {
    if (fingerExtension(landmarks, tip) > 1.55) {
      extended += 1;
    }
  }
  return extended / tips.length;
}

export function pinchRatioOf(landmarks: Vec2[]): number {
  const thumb = landmarks[THUMB_TIP];
  const index = landmarks[INDEX_TIP];
  if (thumb === undefined || index === undefined) {
    return 1;
  }
  return dist(thumb, index) / handScale(landmarks);
}

export function isPointing(landmarks: Vec2[]): boolean {
  const indexExtended = fingerExtension(landmarks, INDEX_TIP) > 1.6;
  const middleFolded = fingerExtension(landmarks, MIDDLE_TIP) < 1.45;
  const ringFolded = fingerExtension(landmarks, RING_TIP) < 1.4;
  const indexStraight = (() => {
    const mcp = landmarks[INDEX_MCP];
    const pip = landmarks[INDEX_PIP];
    const tip = landmarks[INDEX_TIP];
    if (mcp === undefined || pip === undefined || tip === undefined) {
      return false;
    }
    const a = { x: pip.x - mcp.x, y: pip.y - mcp.y };
    const b = { x: tip.x - pip.x, y: tip.y - pip.y };
    const magnitude = Math.hypot(a.x, a.y) * Math.hypot(b.x, b.y);
    if (magnitude < 1e-6) {
      return false;
    }
    return (a.x * b.x + a.y * b.y) / magnitude > 0.75;
  })();
  return indexExtended && indexStraight && middleFolded && ringFolded;
}

type HandMemory = {
  smoother: HandSmoother;
  pinched: boolean;
  palmOpen: boolean;
  lastCenter: Vec2 | null;
  lastTime: number | null;
};

export class GestureRecognizer {
  private readonly memory = new Map<string, HandMemory>();

  /** Feed raw per-frame hands; returns smoothed, hysteresis-stable gestures. */
  update(rawHands: RawHand[], timestampMs: number): GestureFrame {
    const seen = new Set<string>();
    const hands: HandGesture[] = [];

    for (const raw of rawHands) {
      if (raw.score < MIN_SCORE || raw.landmarks.length < 21) {
        continue;
      }
      const key = raw.handedness;
      seen.add(key);
      let memory = this.memory.get(key);
      if (memory === undefined) {
        memory = {
          smoother: new HandSmoother(),
          pinched: false,
          palmOpen: false,
          lastCenter: null,
          lastTime: null,
        };
        this.memory.set(key, memory);
      }
      const landmarks = memory.smoother.smooth(raw.landmarks, timestampMs);
      const wrist = landmarks[WRIST];
      const middle = landmarks[MIDDLE_MCP];
      const center: Vec2 =
        wrist !== undefined && middle !== undefined
          ? { x: (wrist.x + middle.x) / 2, y: (wrist.y + middle.y) / 2 }
          : { x: 0.5, y: 0.5 };

      let velocity: Vec2 = { x: 0, y: 0 };
      if (memory.lastCenter !== null && memory.lastTime !== null) {
        const dt = Math.max(1e-3, (timestampMs - memory.lastTime) / 1000);
        velocity = {
          x: (center.x - memory.lastCenter.x) / dt,
          y: (center.y - memory.lastCenter.y) / dt,
        };
      }
      memory.lastCenter = center;
      memory.lastTime = timestampMs;

      const pinchRatio = pinchRatioOf(landmarks);
      memory.pinched = memory.pinched
        ? pinchRatio < PINCH_RELEASE
        : pinchRatio < PINCH_ENGAGE;

      const openness = opennessOf(landmarks);
      memory.palmOpen = memory.palmOpen
        ? openness > PALM_OPEN_RELEASE
        : openness > PALM_OPEN_ENGAGE;

      hands.push({
        handedness: raw.handedness,
        score: raw.score,
        center,
        velocity,
        pinchRatio,
        pinched: memory.pinched,
        openness,
        palmOpen: memory.palmOpen,
        pointing: !memory.pinched && isPointing(landmarks),
        pointerTip: landmarks[INDEX_TIP] ?? center,
        landmarks,
      });
    }

    for (const [key, memory] of this.memory) {
      if (!seen.has(key)) {
        memory.smoother.reset();
        memory.pinched = false;
        memory.palmOpen = false;
        memory.lastCenter = null;
        memory.lastTime = null;
      }
    }

    let twoHand: TwoHandGesture | null = null;
    const [first, second] = hands;
    if (first !== undefined && second !== undefined) {
      twoHand = {
        span: dist(first.center, second.center),
        angleRad: Math.atan2(
          second.center.y - first.center.y,
          second.center.x - first.center.x,
        ),
        center: {
          x: (first.center.x + second.center.x) / 2,
          y: (first.center.y + second.center.y) / 2,
        },
      };
    }

    return {
      hands,
      twoHand,
      bothPalmsOpen:
        hands.length === 2 && hands.every((hand) => hand.palmOpen),
      timestampMs,
    };
  }

  reset(): void {
    this.memory.clear();
  }
}
