/**
 * HoloConsole interaction state (HOL-002, HOL-003, HOL-004).
 *
 * Discrete interaction state lives here; continuous values (drag deltas,
 * zoom span) stream outside the machine for per-frame use. Activation is
 * deliberate: both palms must stay open for a full summon hold. Cancel is
 * always available and immediate.
 */

import { assign, setup } from "xstate";

export const SUMMON_HOLD_MS = 900;
export const HANDS_LOST_GRACE_MS = 1_200;
export const SUSPEND_TIMEOUT_MS = 5_000;

export type HoloContext = {
  summonProgress: number;
  cancelReason: string | null;
};

export type HoloEvent =
  | { type: "PALMS_OPEN" }
  | { type: "PALMS_LOST" }
  | { type: "SUMMON_TICK"; progress: number }
  | { type: "PINCH_START" }
  | { type: "PINCH_END" }
  | { type: "TWO_HAND_START" }
  | { type: "TWO_HAND_END" }
  | { type: "SCRUB_START" }
  | { type: "SCRUB_END" }
  | { type: "PUSH_BACK" }
  | { type: "HANDS_LOST" }
  | { type: "HANDS_FOUND" }
  | { type: "CANCEL"; reason?: string };

export const holoMachine = setup({
  types: {
    context: {} as HoloContext,
    events: {} as HoloEvent,
  },
  delays: {
    summonHold: SUMMON_HOLD_MS,
    handsGrace: HANDS_LOST_GRACE_MS,
    suspendTimeout: SUSPEND_TIMEOUT_MS,
  },
}).createMachine({
  id: "holo",
  initial: "dormant",
  context: { summonProgress: 0, cancelReason: null },
  on: {
    CANCEL: {
      target: ".dormant",
      actions: assign(({ event }) => ({
        summonProgress: 0,
        cancelReason: event.reason ?? "cancelled",
      })),
    },
  },
  states: {
    dormant: {
      entry: assign({ summonProgress: 0 }),
      on: {
        PALMS_OPEN: "summoning",
      },
    },
    summoning: {
      entry: assign({ summonProgress: 0, cancelReason: null }),
      on: {
        PALMS_LOST: "dormant",
        HANDS_LOST: "dormant",
        SUMMON_TICK: {
          actions: assign(({ event }) => ({
            summonProgress: Math.min(1, event.progress),
          })),
        },
      },
      after: {
        summonHold: "active",
      },
    },
    active: {
      entry: assign({ summonProgress: 1 }),
      initial: "navigate",
      on: {
        PUSH_BACK: "dormant",
        HANDS_LOST: "suspended",
      },
      states: {
        navigate: {
          on: {
            PINCH_START: "dragging",
            TWO_HAND_START: "transforming",
            SCRUB_START: "scrubbing",
          },
        },
        dragging: {
          on: {
            PINCH_END: "navigate",
            TWO_HAND_START: "transforming",
          },
        },
        transforming: {
          on: {
            TWO_HAND_END: "navigate",
          },
        },
        scrubbing: {
          on: {
            SCRUB_END: "navigate",
            PINCH_START: "dragging",
          },
        },
      },
    },
    suspended: {
      on: {
        HANDS_FOUND: "active",
      },
      after: {
        suspendTimeout: "dormant",
      },
    },
  },
});

export type HoloStateValue =
  | "dormant"
  | "summoning"
  | "suspended"
  | { active: "navigate" | "dragging" | "transforming" | "scrubbing" };
