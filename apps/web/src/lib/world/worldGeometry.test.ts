import { describe, expect, it } from "vitest";

import { cameraBus } from "./cameraBus";
import { deriveEdges } from "./relationships";
import { toMap, toStage } from "./space";

describe("toStage", () => {
  it("keeps holograms above the floor", () => {
    expect(toStage([0, -2, 1.25])[1]).toBeGreaterThan(0);
  });

  it("centers the provider depth range on the stage origin", () => {
    expect(toStage([0, 0, 1.25])[2]).toBeCloseTo(0);
    expect(toStage([0, 0, 1.5])[2]).toBeGreaterThan(0);
    expect(toStage([0, 0, 1.0])[2]).toBeLessThan(0);
  });
});

describe("toMap", () => {
  it("projects into the viewport bounds", () => {
    for (const position of [
      [-1, 0, 1.0],
      [1, 0.5, 1.5],
      [0, 0, 1.25],
    ] as [number, number, number][]) {
      const point = toMap(position, 900, 560);
      expect(point.x).toBeGreaterThan(0);
      expect(point.x).toBeLessThan(900);
      expect(point.y).toBeGreaterThan(0);
      expect(point.y).toBeLessThan(560);
    }
  });
});

describe("deriveEdges", () => {
  it("derives near and axis relationships with tolerances", () => {
    const edges = deriveEdges([
      { id: "a", position: [0, 0, 1], confidence: 0.9, presence: "visible" },
      { id: "b", position: [0.3, 0, 1], confidence: 0.8, presence: "visible" },
    ]);
    const kinds = edges.map((edge) => edge.kind);
    expect(kinds).toContain("near");
    expect(kinds).toContain("left_of");
    expect(edges.every((edge) => edge.derived)).toBe(true);
    expect(edges[0]?.confidence).toBeCloseTo(0.8);
  });

  it("skips missing and archived entities", () => {
    const edges = deriveEdges([
      { id: "a", position: [0, 0, 1], confidence: 0.9, presence: "missing" },
      { id: "b", position: [0.2, 0, 1], confidence: 0.8, presence: "visible" },
    ]);
    expect(edges).toHaveLength(0);
  });

  it("does not link distant objects", () => {
    const edges = deriveEdges([
      { id: "a", position: [-1, 0, 1], confidence: 0.9, presence: "visible" },
      { id: "b", position: [1, 0.5, 1.5], confidence: 0.8, presence: "visible" },
    ]);
    expect(edges.filter((edge) => edge.kind === "near")).toHaveLength(0);
  });
});

describe("cameraBus", () => {
  it("clamps zoom and pitch, and versions focus jumps", () => {
    cameraBus.reset();
    const initial = cameraBus.read().focusVersion;
    for (let i = 0; i < 60; i += 1) {
      cameraBus.zoom(0.5);
      cameraBus.orbit(0, -1);
    }
    expect(cameraBus.read().radius).toBeGreaterThanOrEqual(1.2);
    expect(cameraBus.read().phi).toBeGreaterThanOrEqual(0.12);

    for (let i = 0; i < 60; i += 1) {
      cameraBus.zoom(2);
      cameraBus.orbit(0, 1);
    }
    expect(cameraBus.read().radius).toBeLessThanOrEqual(7.5);
    expect(cameraBus.read().phi).toBeLessThanOrEqual(Math.PI * 0.49);

    cameraBus.focus([1, 0.3, 0], 2);
    expect(cameraBus.read().target).toEqual([1, 0.3, 0]);
    expect(cameraBus.read().focusVersion).toBe(initial + 1);
    cameraBus.focus([0, 0.2, 1]);
    expect(cameraBus.read().radius).toBe(2);
    cameraBus.reset();
  });

  it("clamps panning to the stage", () => {
    cameraBus.reset();
    for (let i = 0; i < 100; i += 1) {
      cameraBus.pan(1, 1);
    }
    expect(cameraBus.read().target[0]).toBeLessThanOrEqual(2.2);
    expect(cameraBus.read().target[2]).toBeLessThanOrEqual(2.2);
    cameraBus.reset();
  });
});
