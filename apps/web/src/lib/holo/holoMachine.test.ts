import { describe, expect, it } from "vitest";
import { createActor, SimulatedClock } from "xstate";

import {
  HANDS_LOST_GRACE_MS,
  holoMachine,
  SUMMON_HOLD_MS,
  SUSPEND_TIMEOUT_MS,
} from "./holoMachine";

function start() {
  const clock = new SimulatedClock();
  const actor = createActor(holoMachine, { clock });
  actor.start();
  return { actor, clock };
}

describe("holoMachine", () => {
  it("requires a sustained two-palm hold before activating (HOL-003)", () => {
    const { actor, clock } = start();
    expect(actor.getSnapshot().value).toBe("dormant");

    actor.send({ type: "PALMS_OPEN" });
    expect(actor.getSnapshot().value).toBe("summoning");

    // Dropping the palms early cancels the summon.
    clock.increment(SUMMON_HOLD_MS / 2);
    actor.send({ type: "PALMS_LOST" });
    expect(actor.getSnapshot().value).toBe("dormant");

    // A full hold activates.
    actor.send({ type: "PALMS_OPEN" });
    clock.increment(SUMMON_HOLD_MS + 10);
    expect(actor.getSnapshot().value).toEqual({ active: "navigate" });
  });

  it("tracks summon progress from ticks", () => {
    const { actor } = start();
    actor.send({ type: "PALMS_OPEN" });
    actor.send({ type: "SUMMON_TICK", progress: 0.5 });
    expect(actor.getSnapshot().context.summonProgress).toBe(0.5);
    actor.send({ type: "SUMMON_TICK", progress: 4 });
    expect(actor.getSnapshot().context.summonProgress).toBe(1);
  });

  it("moves between interaction modes", () => {
    const { actor, clock } = start();
    actor.send({ type: "PALMS_OPEN" });
    clock.increment(SUMMON_HOLD_MS + 10);

    actor.send({ type: "PINCH_START" });
    expect(actor.getSnapshot().value).toEqual({ active: "dragging" });
    actor.send({ type: "TWO_HAND_START" });
    expect(actor.getSnapshot().value).toEqual({ active: "transforming" });
    actor.send({ type: "TWO_HAND_END" });
    expect(actor.getSnapshot().value).toEqual({ active: "navigate" });
    actor.send({ type: "SCRUB_START" });
    expect(actor.getSnapshot().value).toEqual({ active: "scrubbing" });
    actor.send({ type: "SCRUB_END" });
    expect(actor.getSnapshot().value).toEqual({ active: "navigate" });
  });

  it("cancel is immediate from any state (HOL-004)", () => {
    const { actor, clock } = start();
    actor.send({ type: "PALMS_OPEN" });
    clock.increment(SUMMON_HOLD_MS + 10);
    actor.send({ type: "PINCH_START" });
    actor.send({ type: "CANCEL", reason: "operator" });
    const snapshot = actor.getSnapshot();
    expect(snapshot.value).toBe("dormant");
    expect(snapshot.context.cancelReason).toBe("operator");

    actor.send({ type: "PALMS_OPEN" });
    actor.send({ type: "CANCEL" });
    expect(actor.getSnapshot().context.cancelReason).toBe("cancelled");
  });

  it("suspends on hand loss and expires back to dormant", () => {
    const { actor, clock } = start();
    actor.send({ type: "PALMS_OPEN" });
    clock.increment(SUMMON_HOLD_MS + 10);
    actor.send({ type: "HANDS_LOST" });
    expect(actor.getSnapshot().value).toBe("suspended");

    actor.send({ type: "HANDS_FOUND" });
    expect(actor.getSnapshot().value).toEqual({ active: "navigate" });

    actor.send({ type: "HANDS_LOST" });
    clock.increment(SUSPEND_TIMEOUT_MS + 10);
    expect(actor.getSnapshot().value).toBe("dormant");
    // Grace constant is exported for the overlay's debouncing.
    expect(HANDS_LOST_GRACE_MS).toBeGreaterThan(0);
  });

  it("push-back returns to dormant from active", () => {
    const { actor, clock } = start();
    actor.send({ type: "PALMS_OPEN" });
    clock.increment(SUMMON_HOLD_MS + 10);
    actor.send({ type: "PUSH_BACK" });
    expect(actor.getSnapshot().value).toBe("dormant");
  });
});
