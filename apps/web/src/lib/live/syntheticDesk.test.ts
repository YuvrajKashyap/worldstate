import { describe, expect, it } from "vitest";

import { objectCenter } from "./syntheticDesk";

describe("objectCenter", () => {
  it("matches the backend replay provider phase math", () => {
    // Mirrors ReplayPerceptionProvider.observe for index 0 at sequence 10.
    const width = 960;
    const height = 540;
    const sequence = 10;
    const phase = sequence * 0.012;
    const expected = {
      x: width * 0.25 + Math.sin(phase) * width * 0.06,
      y: height * 0.42 + Math.sin(phase * 0.7) * height * 0.03,
    };
    const actual = objectCenter(0, sequence, width, height);
    expect(actual.x).toBeCloseTo(expected.x);
    expect(actual.y).toBeCloseTo(expected.y);
  });

  it("keeps every object inside the frame across the replay", () => {
    for (let sequence = 0; sequence < 240; sequence += 1) {
      for (let index = 0; index < 3; index += 1) {
        const { x, y } = objectCenter(index, sequence, 960, 540);
        expect(x).toBeGreaterThan(0);
        expect(x).toBeLessThan(960);
        expect(y).toBeGreaterThan(0);
        expect(y).toBeLessThan(540);
      }
    }
  });
});
