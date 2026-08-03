import { describe, expect, it } from "vitest";

import {
  estimateMotion,
  projectBox,
  projectPosition,
  type MotionSample,
} from "./prediction";

function sample(at: number, offset: number): MotionSample {
  return {
    at,
    presence: "visible",
    box: [10 + offset, 20 + offset, 30 + offset, 40 + offset],
    position: [offset / 100, 0, 1],
  };
}

describe("motion prediction", () => {
  it("estimates velocity over recent observations and projects smoothly", () => {
    const motion = estimateMotion([
      sample(1_000, 0),
      sample(1_050, 5),
      sample(1_100, 10),
    ]);
    expect(motion).not.toBeNull();
    expect(motion?.boxVelocity?.[0]).toBeCloseTo(0.1);
    expect(motion?.positionVelocity?.[0]).toBeCloseTo(0.001);
    expect(projectBox([20, 30, 40, 50], motion?.boxVelocity ?? null, 1_100, 1_150)).toEqual([
      25,
      35,
      45,
      55,
    ]);
    expect(
      projectPosition([0.1, 0, 1], motion?.positionVelocity ?? null, 1_100, 1_150)[0],
    ).toBeCloseTo(0.15);
  });

  it("caps prediction horizon so a stalled backend cannot drift forever", () => {
    const projected = projectBox(
      [0, 0, 10, 10],
      [0.1, 0.1, 0.1, 0.1],
      1_000,
      2_000,
    );
    expect(projected).toEqual([12, 12, 22, 22]);
  });

  it("does not infer motion through occlusion or from one sample", () => {
    expect(estimateMotion([sample(1_000, 0)])?.boxVelocity).toBeNull();
    expect(
      estimateMotion([
        sample(1_000, 0),
        { ...sample(1_050, 5), presence: "occluded" },
      ]),
    ).toBeNull();
  });
});
