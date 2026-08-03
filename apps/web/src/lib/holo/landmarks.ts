/** Hand landmark types and smoothing for HoloConsole (HOL-001). */

export type Vec2 = { x: number; y: number };

/** 21 normalized MediaPipe hand landmarks (image space, 0..1). */
export type RawHand = {
  landmarks: Vec2[];
  handedness: "Left" | "Right";
  score: number;
};

export const WRIST = 0;
export const THUMB_TIP = 4;
export const INDEX_MCP = 5;
export const INDEX_PIP = 6;
export const INDEX_TIP = 8;
export const MIDDLE_MCP = 9;
export const MIDDLE_TIP = 12;
export const RING_TIP = 16;
export const PINKY_TIP = 20;

/**
 * One-Euro filter: velocity-adaptive low-pass. Slow movement gets heavy
 * smoothing (no jitter); fast movement tracks tightly (no lag).
 */
export class OneEuroFilter {
  private lastValue: number | null = null;
  private lastDerivative = 0;
  private lastTime: number | null = null;

  constructor(
    private readonly minCutoff = 1.4,
    private readonly beta = 0.6,
    private readonly derivativeCutoff = 1.0,
  ) {}

  private static alpha(cutoff: number, dt: number): number {
    const tau = 1 / (2 * Math.PI * cutoff);
    return 1 / (1 + tau / dt);
  }

  filter(value: number, timestampMs: number): number {
    if (this.lastValue === null || this.lastTime === null) {
      this.lastValue = value;
      this.lastTime = timestampMs;
      return value;
    }
    const dt = Math.max(1e-3, (timestampMs - this.lastTime) / 1000);
    this.lastTime = timestampMs;

    const derivative = (value - this.lastValue) / dt;
    const derivativeAlpha = OneEuroFilter.alpha(this.derivativeCutoff, dt);
    this.lastDerivative =
      derivativeAlpha * derivative + (1 - derivativeAlpha) * this.lastDerivative;

    const cutoff = this.minCutoff + this.beta * Math.abs(this.lastDerivative);
    const valueAlpha = OneEuroFilter.alpha(cutoff, dt);
    this.lastValue = valueAlpha * value + (1 - valueAlpha) * this.lastValue;
    return this.lastValue;
  }

  reset(): void {
    this.lastValue = null;
    this.lastDerivative = 0;
    this.lastTime = null;
  }
}

/** Per-hand smoother: one filter pair per landmark, reset on hand loss. */
export class HandSmoother {
  private readonly filters: { x: OneEuroFilter; y: OneEuroFilter }[] = [];

  smooth(landmarks: Vec2[], timestampMs: number): Vec2[] {
    while (this.filters.length < landmarks.length) {
      this.filters.push({ x: new OneEuroFilter(), y: new OneEuroFilter() });
    }
    return landmarks.map((point, index) => {
      const pair = this.filters[index];
      if (pair === undefined) {
        return point;
      }
      return {
        x: pair.x.filter(point.x, timestampMs),
        y: pair.y.filter(point.y, timestampMs),
      };
    });
  }

  reset(): void {
    for (const pair of this.filters) {
      pair.x.reset();
      pair.y.reset();
    }
  }
}
