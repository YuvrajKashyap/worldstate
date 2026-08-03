import { describe, expect, it } from "vitest";

import { deriveSupportSurfaces, type SupportEntity } from "./supportSurfaces";

function entity(id: string, y: number, x: number, label = "keys"): SupportEntity {
  return {
    id,
    label,
    presence: "visible",
    confidence: 0.8,
    uncertainty: 0.2,
    position: [x, y, 1.1],
    bounds: [0.15, 0.08, 0.08],
    hidden: false,
  };
}

describe("support surface inference", () => {
  it("clusters multiple object contacts into one measured support tier", () => {
    const surfaces = deriveSupportSurfaces([
      entity("keys", 0.1, -0.2),
      entity("wallet", 0.11, 0.2, "wallet"),
    ]);
    expect(surfaces).toHaveLength(1);
    expect(surfaces[0]?.evidenceCount).toBe(2);
    expect(surfaces[0]?.width).toBeGreaterThanOrEqual(0.5);
  });

  it("keeps distinct desk heights as distinct support tiers", () => {
    const surfaces = deriveSupportSurfaces([
      entity("low-a", -0.2, -0.2),
      entity("low-b", -0.19, 0.1),
      entity("high-a", 0.25, -0.1, "earbuds"),
      entity("high-b", 0.26, 0.2, "wallet"),
    ]);
    expect(surfaces).toHaveLength(2);
    const heights = surfaces.map((surface) => surface.center[1]);
    expect(Math.abs((heights[1] ?? 0) - (heights[0] ?? 0))).toBeGreaterThan(0.3);
  });

  it("does not invent a plane from one object or wall-mounted evidence", () => {
    expect(deriveSupportSurfaces([entity("solo", 0.1, 0)])).toEqual([]);
    expect(deriveSupportSurfaces([
      entity("board-a", 0.3, -0.2, "whiteboard"),
      entity("board-b", 0.31, 0.2, "wall decoration"),
    ])).toEqual([]);
  });
});
