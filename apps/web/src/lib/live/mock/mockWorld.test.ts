import { describe, expect, it } from "vitest";

import { MOCK_FPS, MockWorldEngine } from "./mockWorld";

const at = (sequence: number) =>
  new Date(1_700_000_000_000 + sequence * (1000 / MOCK_FPS)).toISOString();

function runUntil(engine: MockWorldEngine, sequence: number) {
  let last = engine.tick(0, at(0));
  for (let i = 1; i <= sequence; i += 1) {
    last = engine.tick(i, at(i));
  }
  return last;
}

describe("MockWorldEngine", () => {
  it("is deterministic for the same sequence", () => {
    const a = runUntil(new MockWorldEngine(), 40);
    const b = runUntil(new MockWorldEngine(), 40);
    expect(a).toEqual(b);
  });

  it("adds all three objects on the first frame", () => {
    const engine = new MockWorldEngine();
    const first = engine.tick(0, at(0));
    expect(first.objects.map((object) => object.label)).toEqual([
      "cup",
      "book",
      "phone",
    ]);
    expect(first.events.filter((event) => event.kind === "added")).toHaveLength(3);
    for (const event of first.events) {
      expect(event.id).toHaveLength(36);
      expect(event.scene_id).toHaveLength(36);
      expect(event.entity_id).toHaveLength(36);
    }
  });

  it("runs the scripted book disappearance and rediscovery", () => {
    const engine = new MockWorldEngine();
    const occludedTick = runUntil(engine, 12 * MOCK_FPS + 1);
    const book = occludedTick.objects.find((object) => object.label === "book");
    expect(book?.presence).toBe("occluded");

    let sawRemoved = false;
    let sawRediscovered = false;
    let missingPresence = false;
    for (let sequence = 12 * MOCK_FPS + 2; sequence <= 19 * MOCK_FPS; sequence += 1) {
      const tick = engine.tick(sequence, at(sequence));
      const bookNow = tick.objects.find((object) => object.label === "book");
      if (bookNow?.presence === "missing") {
        missingPresence = true;
      }
      for (const event of tick.events) {
        if (event.kind === "removed") {
          sawRemoved = true;
        }
        if (event.kind === "rediscovered") {
          sawRediscovered = true;
        }
      }
    }
    expect(missingPresence).toBe(true);
    expect(sawRemoved).toBe(true);
    expect(sawRediscovered).toBe(true);
  });

  it("decays confidence while the book is unobserved", () => {
    const engine = new MockWorldEngine();
    const before = runUntil(engine, 12 * MOCK_FPS - 1);
    const confidentBook = before.objects.find((object) => object.label === "book");
    let last = before;
    for (let sequence = 12 * MOCK_FPS; sequence <= 17 * MOCK_FPS; sequence += 1) {
      last = engine.tick(sequence, at(sequence));
    }
    const decayedBook = last.objects.find((object) => object.label === "book");
    expect(decayedBook !== undefined && confidentBook !== undefined).toBe(true);
    if (decayedBook !== undefined && confidentBook !== undefined) {
      expect(decayedBook.confidence).toBeLessThan(confidentBook.confidence);
      expect(decayedBook.uncertainty).toBeGreaterThan(confidentBook.uncertainty);
    }
  });

  it("emits moved events as the cup drifts", () => {
    const engine = new MockWorldEngine();
    let movedEvents = 0;
    for (let sequence = 0; sequence <= 10 * MOCK_FPS; sequence += 1) {
      const tick = engine.tick(sequence, at(sequence));
      movedEvents += tick.events.filter((event) => event.kind === "moved").length;
    }
    expect(movedEvents).toBeGreaterThan(0);
  });

  it("freezes the box and position while unobserved", () => {
    const engine = new MockWorldEngine();
    runUntil(engine, 12 * MOCK_FPS + 1);
    const a = engine.tick(12 * MOCK_FPS + 2, at(12 * MOCK_FPS + 2));
    const b = engine.tick(12 * MOCK_FPS + 3, at(12 * MOCK_FPS + 3));
    const bookA = a.objects.find((object) => object.label === "book");
    const bookB = b.objects.find((object) => object.label === "book");
    expect(bookA?.position_m).toEqual(bookB?.position_m);
    expect(bookA?.box_xyxy).toEqual(bookB?.box_xyxy);
  });
});
