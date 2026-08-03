import { describe, expect, it } from "vitest";

import type { RawHand, Vec2 } from "./landmarks";
import {
  GestureRecognizer,
  isPointing,
  opennessOf,
  pinchRatioOf,
} from "./recognizer";

/**
 * Synthetic hand builder. Wrist at (0.5, 0.8), middle MCP at (0.5, 0.72):
 * the hand scale is 0.08 in normalized image space.
 */
function buildHand(options: {
  open?: boolean;
  pinchDistance?: number;
  pointing?: boolean;
  shiftX?: number;
}): Vec2[] {
  const shift = options.shiftX ?? 0;
  const wrist: Vec2 = { x: 0.5 + shift, y: 0.8 };
  const points: Vec2[] = Array.from({ length: 21 }, () => ({
    x: wrist.x,
    y: wrist.y - 0.09,
  }));
  points[0] = wrist;
  points[9] = { x: wrist.x, y: 0.72 }; // middle MCP → scale 0.08

  const tipOffset = options.open ? 0.16 : 0.09;
  points[8] = { x: wrist.x - 0.01, y: wrist.y - tipOffset };
  points[12] = { x: wrist.x, y: wrist.y - tipOffset };
  points[16] = { x: wrist.x + 0.01, y: wrist.y - tipOffset };
  points[20] = { x: wrist.x + 0.02, y: wrist.y - tipOffset };
  points[4] = { x: wrist.x - 0.05, y: wrist.y - 0.06 };

  if (options.pointing === true) {
    points[5] = { x: wrist.x - 0.01, y: wrist.y - 0.08 };
    points[6] = { x: wrist.x - 0.01, y: wrist.y - 0.14 };
    points[7] = { x: wrist.x - 0.01, y: wrist.y - 0.17 };
    points[8] = { x: wrist.x - 0.01, y: wrist.y - 0.2 };
    points[12] = { x: wrist.x, y: wrist.y - 0.09 };
    points[16] = { x: wrist.x + 0.01, y: wrist.y - 0.09 };
  }

  if (options.pinchDistance !== undefined) {
    points[8] = { x: wrist.x, y: wrist.y - 0.16 };
    points[4] = {
      x: wrist.x,
      y: wrist.y - 0.16 + options.pinchDistance,
    };
  }
  return points;
}

function rawHand(
  landmarks: Vec2[],
  handedness: "Left" | "Right" = "Right",
  score = 0.95,
): RawHand {
  return { landmarks, handedness, score };
}

describe("geometric features", () => {
  it("scores open palms high and fists low", () => {
    expect(opennessOf(buildHand({ open: true }))).toBeGreaterThan(0.75);
    expect(opennessOf(buildHand({ open: false }))).toBeLessThan(0.3);
  });

  it("computes pinch ratio relative to hand scale", () => {
    // 0.016 distance / 0.08 scale = 0.2
    expect(
      pinchRatioOf(buildHand({ pinchDistance: 0.016 })),
    ).toBeCloseTo(0.2, 1);
    expect(
      pinchRatioOf(buildHand({ pinchDistance: 0.08 })),
    ).toBeCloseTo(1.0, 1);
  });

  it("detects a pointing index with folded companions", () => {
    expect(isPointing(buildHand({ pointing: true }))).toBe(true);
    expect(isPointing(buildHand({ open: true }))).toBe(false);
    expect(isPointing(buildHand({ open: false }))).toBe(false);
  });
});

describe("GestureRecognizer", () => {
  /**
   * The recognizer smooths landmarks with a one-euro filter, so a pose must
   * be held for a few frames before geometry converges — exactly the
   * accidental-trigger suppression the spec asks for. `settle` holds one
   * pose for `frames` frames at 30 fps and returns the last gesture frame.
   */
  function makeSettler(recognizer: GestureRecognizer) {
    let clock = 0;
    const step = (landmarks: Vec2[]) => {
      clock += 33;
      return recognizer.update([rawHand(landmarks)], clock);
    };
    const settle = (landmarks: Vec2[], frames = 12) => {
      let last = step(landmarks);
      for (let i = 1; i < frames; i += 1) {
        last = step(landmarks);
      }
      return last;
    };
    return { step, settle };
  }

  it("applies pinch hysteresis: engage below 0.34, release above 0.46", () => {
    const recognizer = new GestureRecognizer();
    const { settle } = makeSettler(recognizer);

    // ratio 0.625 → open
    expect(settle(buildHand({ pinchDistance: 0.05 })).hands[0]?.pinched).toBe(false);
    // ratio 0.25 < 0.34 → engage
    expect(settle(buildHand({ pinchDistance: 0.02 })).hands[0]?.pinched).toBe(true);
    // ratio ~0.41 < release 0.46 → hold (hysteresis)
    expect(settle(buildHand({ pinchDistance: 0.033 })).hands[0]?.pinched).toBe(true);
    // ratio 0.75 > 0.46 → release
    expect(settle(buildHand({ pinchDistance: 0.06 })).hands[0]?.pinched).toBe(false);
  });

  it("requires a sustained open palm before reporting palmOpen", () => {
    const recognizer = new GestureRecognizer();
    const { step, settle } = makeSettler(recognizer);
    expect(settle(buildHand({ open: false })).hands[0]?.palmOpen).toBe(false);
    // A single open frame is not enough: smoothing suppresses flicker.
    expect(step(buildHand({ open: true })).hands[0]?.palmOpen).toBe(false);
    // A held-open palm converges and engages.
    expect(settle(buildHand({ open: true }), 20).hands[0]?.palmOpen).toBe(true);
  });

  it("drops low-confidence hands", () => {
    const recognizer = new GestureRecognizer();
    const frame = recognizer.update(
      [rawHand(buildHand({ open: true }), "Right", 0.3)],
      0,
    );
    expect(frame.hands).toHaveLength(0);
  });

  it("reports two-hand span and both-palms state", () => {
    const recognizer = new GestureRecognizer();
    const frame = recognizer.update(
      [
        rawHand(buildHand({ open: true, shiftX: -0.2 }), "Left"),
        rawHand(buildHand({ open: true, shiftX: 0.2 }), "Right"),
      ],
      0,
    );
    expect(frame.twoHand).not.toBeNull();
    expect(frame.twoHand?.span).toBeCloseTo(0.4, 1);
    expect(frame.bothPalmsOpen).toBe(true);
  });

  it("estimates velocity between frames", () => {
    const recognizer = new GestureRecognizer();
    recognizer.update([rawHand(buildHand({ open: true, shiftX: 0 }))], 0);
    const moved = recognizer.update(
      [rawHand(buildHand({ open: true, shiftX: 0.1 }))],
      100,
    );
    // 0.1 normalized units in 100ms ≈ 1.0 units/s (smoothing reduces it).
    expect(moved.hands[0]?.velocity.x).toBeGreaterThan(0.3);
  });
});
