import { describe, expect, it } from "vitest";

import {
  DEFAULT_LIVE_PROMPTS,
  MAX_OBJECT_PROMPTS,
  normalizeObjectPrompts,
  parseObjectPrompts,
} from "./prompts";

describe("live object prompts", () => {
  it("ships a broad editable inventory vocabulary at the backend limit", () => {
    expect(DEFAULT_LIVE_PROMPTS).toContain("computer mouse");
    expect(DEFAULT_LIVE_PROMPTS).toContain("phone");
    expect(DEFAULT_LIVE_PROMPTS).toContain("notebook");
    expect(DEFAULT_LIVE_PROMPTS).toContain("bottle");
    expect(DEFAULT_LIVE_PROMPTS).toContain("person");
    expect(DEFAULT_LIVE_PROMPTS).toContain("earbuds");
    expect(DEFAULT_LIVE_PROMPTS).toContain("keys");
    expect(DEFAULT_LIVE_PROMPTS).toContain("card");
    expect(DEFAULT_LIVE_PROMPTS).toContain("wallet");
    expect(DEFAULT_LIVE_PROMPTS).toContain("whiteboard");
    expect(DEFAULT_LIVE_PROMPTS).toContain("wall decoration");
    expect(new Set(DEFAULT_LIVE_PROMPTS).size).toBe(MAX_OBJECT_PROMPTS);
    expect(DEFAULT_LIVE_PROMPTS).toHaveLength(MAX_OBJECT_PROMPTS);
  });

  it("normalizes, deduplicates, and removes empty targets", () => {
    expect(parseObjectPrompts(" Mug,  CELL   PHONE, mug, , keys ")).toEqual([
      "mug",
      "cell phone",
      "keys",
    ]);
  });

  it("enforces the protocol prompt limit", () => {
    const prompts = Array.from({ length: 40 }, (_, index) => `object ${String(index)}`);
    expect(normalizeObjectPrompts(prompts)).toHaveLength(MAX_OBJECT_PROMPTS);
  });
});
