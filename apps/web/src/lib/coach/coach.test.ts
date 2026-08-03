import { describe, expect, it } from "vitest";

import { adviseCoach } from "./coach";
import type { EntityRecord } from "../../state/worldStore";

const NOW = 1_700_000_000_000;

function record(overrides: Partial<EntityRecord> = {}): EntityRecord {
  return {
    id: "e1",
    label: "cup",
    firstSeenAt: NOW - 60_000,
    lastSeenAt: NOW,
    lastVisibleAt: NOW,
    presence: "visible",
    confidence: 0.9,
    uncertainty: 0.1,
    position: [0, 0, 1],
    bounds: null,
    box: [0, 0, 10, 10],
    history: [],
    eventCount: 0,
    ...overrides,
  };
}

const goodQuality = {
  sharpness: 0.8,
  exposure: 0.95,
  brightness: 0.5,
  contrast: 0.6,
  keyframe_score: 0.8,
};

describe("adviseCoach", () => {
  it("asks to hold still when motion blur is high", () => {
    const directives = adviseCoach({
      quality: { ...goodQuality, sharpness: 0.1 },
      entities: {},
      order: [],
      updatesPerSecond: 8,
      nowMs: NOW,
    });
    expect(directives.map((d) => d.id)).toContain("hold-still");
    expect(directives[0]?.severity).toBe("act");
  });

  it("asks for light when under-exposed and warns about glare", () => {
    const dark = adviseCoach({
      quality: { ...goodQuality, exposure: 0.4, brightness: 0.1 },
      entities: {},
      order: [],
      updatesPerSecond: 8,
      nowMs: NOW,
    });
    expect(dark.map((d) => d.id)).toContain("add-light");

    const bright = adviseCoach({
      quality: { ...goodQuality, brightness: 0.95 },
      entities: {},
      order: [],
      updatesPerSecond: 8,
      nowMs: NOW,
    });
    expect(bright.map((d) => d.id)).toContain("cut-glare");
  });

  it("suggests revisiting stale objects by name", () => {
    const stale = record({ id: "e2", label: "book", lastVisibleAt: NOW - 30_000 });
    const directives = adviseCoach({
      quality: goodQuality,
      entities: { e2: stale },
      order: ["e2"],
      updatesPerSecond: 8,
      nowMs: NOW,
    });
    const revisit = directives.find((d) => d.id === "revisit-e2");
    expect(revisit?.headline).toContain("book");
  });

  it("suggests revisiting highly uncertain objects", () => {
    const uncertain = record({ id: "e3", label: "phone", uncertainty: 0.8 });
    const directives = adviseCoach({
      quality: goodQuality,
      entities: { e3: uncertain },
      order: ["e3"],
      updatesPerSecond: 8,
      nowMs: NOW,
    });
    expect(directives.some((d) => d.id === "revisit-e3")).toBe(true);
  });

  it("settles into parallax advice when everything is healthy", () => {
    const directives = adviseCoach({
      quality: goodQuality,
      entities: { e1: record() },
      order: ["e1"],
      updatesPerSecond: 8,
      nowMs: NOW,
    });
    expect(directives).toHaveLength(1);
    expect(directives[0]?.id).toBe("parallax");
    expect(directives[0]?.severity).toBe("settle");
  });

  it("declares coverage stable at low update rates", () => {
    const directives = adviseCoach({
      quality: goodQuality,
      entities: {},
      order: [],
      updatesPerSecond: 2,
      nowMs: NOW,
    });
    expect(directives[0]?.id).toBe("coverage-ok");
  });

  it("caps output at two directives", () => {
    const stale = record({ id: "e2", label: "book", lastVisibleAt: NOW - 30_000 });
    const directives = adviseCoach({
      quality: { sharpness: 0.05, exposure: 0.3, brightness: 0.05, keyframe_score: 0.1 },
      entities: { e2: stale },
      order: ["e2"],
      updatesPerSecond: 8,
      nowMs: NOW,
    });
    expect(directives.length).toBeLessThanOrEqual(2);
  });
});
