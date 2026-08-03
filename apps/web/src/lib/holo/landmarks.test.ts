import { describe, expect, it } from "vitest";

import { HandSmoother, OneEuroFilter } from "./landmarks";

describe("OneEuroFilter", () => {
  it("passes the first sample through unchanged", () => {
    const filter = new OneEuroFilter();
    expect(filter.filter(0.42, 0)).toBe(0.42);
  });

  it("suppresses jitter around a steady value", () => {
    const filter = new OneEuroFilter();
    filter.filter(0.5, 0);
    let value = 0.5;
    for (let i = 1; i <= 30; i += 1) {
      value = filter.filter(0.5 + (i % 2 === 0 ? 0.01 : -0.01), i * 33);
    }
    expect(Math.abs(value - 0.5)).toBeLessThan(0.008);
  });

  it("tracks fast movement with limited lag", () => {
    const filter = new OneEuroFilter();
    filter.filter(0, 0);
    let value = 0;
    for (let i = 1; i <= 10; i += 1) {
      value = filter.filter(i * 0.1, i * 33);
    }
    // Ends at 1.0 raw; velocity-adaptive cutoff keeps us close.
    expect(value).toBeGreaterThan(0.8);
  });

  it("resets to pass-through", () => {
    const filter = new OneEuroFilter();
    filter.filter(1, 0);
    filter.reset();
    expect(filter.filter(0, 33)).toBe(0);
  });
});

describe("HandSmoother", () => {
  it("smooths each landmark independently", () => {
    const smoother = new HandSmoother();
    const first = smoother.smooth(
      [
        { x: 0.1, y: 0.1 },
        { x: 0.9, y: 0.9 },
      ],
      0,
    );
    expect(first[0]).toEqual({ x: 0.1, y: 0.1 });
    const second = smoother.smooth(
      [
        { x: 0.2, y: 0.1 },
        { x: 0.8, y: 0.9 },
      ],
      33,
    );
    expect(second[0]?.x).toBeGreaterThan(0.1);
    expect(second[0]?.x).toBeLessThanOrEqual(0.2);
    expect(second[1]?.x).toBeLessThan(0.9);
  });
});
