import { describe, expect, it } from "vitest";

import {
  eventColor,
  eventGlyph,
  palette,
  presenceColor,
  presenceLabel,
} from "./palette";
import {
  dealIn,
  gravitationalEase,
  microSwap,
  popSpring,
  settleSpring,
  slowReveal,
  unseal,
} from "./motion/presets";

const PRESENCES = [
  "visible",
  "occluded",
  "predicted",
  "missing",
  "rediscovered",
  "archived",
] as const;

const EVENT_KINDS = [
  "added",
  "moved",
  "rotated",
  "removed",
  "occluded",
  "rediscovered",
  "confidence_changed",
] as const;

describe("visual grammar completeness", () => {
  it("maps every presence state to a color and label", () => {
    for (const presence of PRESENCES) {
      expect(presenceColor[presence]).toMatch(/^#[0-9a-f]{6}$/i);
      expect(presenceLabel[presence].length).toBeGreaterThan(0);
    }
  });

  it("maps every event kind to a pulse color and glyph", () => {
    for (const kind of EVENT_KINDS) {
      expect(eventColor[kind]).toMatch(/^#[0-9a-f]{6}$/i);
      expect(eventGlyph[kind].length).toBeGreaterThan(0);
    }
  });

  it("missing state is visually alarming, not the accent color", () => {
    expect(presenceColor.missing).toBe(palette.alarm);
    expect(presenceColor.missing).not.toBe(presenceColor.visible);
  });
});

describe("motion vocabulary", () => {
  it("exposes the house easing and springs", () => {
    expect(gravitationalEase).toEqual([0.16, 1, 0.3, 1]);
    expect(settleSpring.type).toBe("spring");
    expect(popSpring.stiffness).toBeGreaterThan(settleSpring.stiffness);
    expect(slowReveal.duration).toBeGreaterThan(0.5);
    expect(microSwap.duration).toBeLessThan(0.2);
    expect(dealIn.visible.transition.ease).toBe(gravitationalEase);
    expect(unseal.visible.clipPath).toContain("0%");
  });
});
