/**
 * HoloConsole: Iron Man-style gesture control over the memory volume.
 *
 * Landmarks are processed entirely in the browser (HOL-001). Recognition
 * (recognizer) is separate from interaction state (holoMachine) (HOL-002).
 * Activation requires a deliberate two-palm summon hold (HOL-003); the
 * gesture confidence and an immediate cancel are always visible (HOL-004).
 * Every control here has keyboard parity in KeyboardLayer.
 *
 * Vocabulary while active:
 *   point ............ steer the reticle; nearest hologram highlights
 *   pinch ............ select the highlighted object / drag to orbit
 *   two hands ........ spread to enlarge, converge to shrink, twist to spin
 *   open-palm swipe .. scrub time backward / forward
 *   both palms push .. return to the present and dismiss
 */

import { useMachine } from "@xstate/react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";
import * as THREE from "three";

import { createHandTracker, type TrackerOutcome } from "../../lib/holo/handTracker";
import { holoMachine, SUMMON_HOLD_MS } from "../../lib/holo/holoMachine";
import {
  GestureRecognizer,
  type GestureFrame,
} from "../../lib/holo/recognizer";
import { microSwap, popSpring } from "../../lib/motion/presets";
import { palette } from "../../lib/palette";
import { cameraBus } from "../../lib/world/cameraBus";
import { toStage } from "../../lib/world/space";
import { useSessionStore } from "../../state/sessionStore";
import { useUiStore } from "../../state/uiStore";
import { useWorldStore } from "../../state/worldStore";

const HAND_LINKS: [number, number][] = [
  [0, 1], [1, 2], [2, 3], [3, 4],
  [0, 5], [5, 6], [6, 7], [7, 8],
  [5, 9], [9, 10], [10, 11], [11, 12],
  [9, 13], [13, 14], [14, 15], [15, 16],
  [13, 17], [17, 18], [18, 19], [19, 20],
  [0, 17],
];

type GestureRuntime = {
  recognizer: GestureRecognizer;
  lastFrame: GestureFrame | null;
  palmsOpenSince: number | null;
  pinchActive: boolean;
  twoHandActive: boolean;
  scrubActive: boolean;
  lastPinchCenter: { x: number; y: number } | null;
  lastSpan: number | null;
  lastAngle: number | null;
  lastHandScale: number | null;
  hoverEntityId: string | null;
};

function projectEntities(
  width: number,
  height: number,
): { id: string; x: number; y: number }[] {
  const intent = cameraBus.read();
  const camera = new THREE.PerspectiveCamera(46, width / height, 0.1, 40);
  const sinPhi = Math.sin(intent.phi);
  camera.position.set(
    intent.target[0] + intent.radius * sinPhi * Math.sin(intent.theta),
    intent.target[1] + intent.radius * Math.cos(intent.phi),
    intent.target[2] + intent.radius * sinPhi * Math.cos(intent.theta),
  );
  camera.lookAt(new THREE.Vector3(...intent.target));
  camera.updateMatrixWorld();

  const { entities, order } = useWorldStore.getState();
  const projected: { id: string; x: number; y: number }[] = [];
  for (const id of order) {
    const record = entities[id];
    if (record?.position == null) {
      continue;
    }
    const stage = toStage(record.position);
    const vector = new THREE.Vector3(...stage).project(camera);
    if (vector.z > 1) {
      continue;
    }
    projected.push({
      id,
      x: (vector.x * 0.5 + 0.5) * width,
      y: (-vector.y * 0.5 + 0.5) * height,
    });
  }
  return projected;
}

export function HoloOverlay() {
  const reduced = useReducedMotion() ?? false;
  const holoActive = useUiStore((state) => state.holoActive);
  const setHoloActive = useUiStore((state) => state.setHoloActive);
  const webcamVideo = useSessionStore((state) => state.webcamVideo);
  const liveStatus = useSessionStore((state) => state.liveStatus);

  const [trackerOutcome, setTrackerOutcome] = useState<TrackerOutcome | null>(
    null,
  );
  const [confidence, setConfidence] = useState(0);
  const [snapshot, send, actor] = useMachine(holoMachine);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const runtime = useRef<GestureRuntime>({
    recognizer: new GestureRecognizer(),
    lastFrame: null,
    palmsOpenSince: null,
    pinchActive: false,
    twoHandActive: false,
    scrubActive: false,
    lastPinchCenter: null,
    lastSpan: null,
    lastAngle: null,
    lastHandScale: null,
    hoverEntityId: null,
  });

  const machineState = snapshot.value;
  const isActive = typeof machineState === "object";
  const activeMode = isActive ? Object.values(machineState)[0] : null;
  const modeName = typeof activeMode === "string" ? activeMode : "navigate";

  // Acquire the tracker when the console opens with a webcam available.
  useEffect(() => {
    if (!holoActive || webcamVideo === null) {
      return;
    }
    const state = runtime.current;
    let cancelled = false;
    let outcome: TrackerOutcome | null = null;
    void createHandTracker().then((result) => {
      if (cancelled) {
        if (result.status === "ready") {
          result.tracker.close();
        }
        return;
      }
      outcome = result;
      setTrackerOutcome(result);
    });
    return () => {
      cancelled = true;
      if (outcome?.status === "ready") {
        outcome.tracker.close();
      }
      state.recognizer.reset();
      setTrackerOutcome(null);
      send({ type: "CANCEL", reason: "console closed" });
    };
  }, [holoActive, webcamVideo, send]);

  const applyGestures = useCallback(
    (frame: GestureFrame, width: number, height: number) => {
      const state = runtime.current;
      const ui = useUiStore.getState();
      const active = typeof actor.getSnapshot().value === "object";

      // Summon lifecycle.
      if (frame.bothPalmsOpen) {
        if (state.palmsOpenSince === null) {
          state.palmsOpenSince = frame.timestampMs;
          send({ type: "PALMS_OPEN" });
        } else {
          send({
            type: "SUMMON_TICK",
            progress:
              (frame.timestampMs - state.palmsOpenSince) / SUMMON_HOLD_MS,
          });
        }
      } else if (state.palmsOpenSince !== null && !active) {
        state.palmsOpenSince = null;
        send({ type: "PALMS_LOST" });
      }

      if (frame.hands.length === 0) {
        send({ type: "HANDS_LOST" });
        state.hoverEntityId = null;
        return;
      }
      send({ type: "HANDS_FOUND" });

      if (!active) {
        return;
      }

      const [first] = frame.hands;
      const two = frame.twoHand;

      // Two-hand transform: spread to enlarge, twist to rotate.
      if (two !== null && frame.hands.every((hand) => !hand.palmOpen)) {
        if (!state.twoHandActive) {
          state.twoHandActive = true;
          state.lastSpan = two.span;
          state.lastAngle = two.angleRad;
          send({ type: "TWO_HAND_START" });
        } else if (state.lastSpan !== null && state.lastAngle !== null) {
          const spanDelta = two.span - state.lastSpan;
          const angleDelta = two.angleRad - state.lastAngle;
          if (Math.abs(spanDelta) > 0.002) {
            cameraBus.zoom(1 - spanDelta * 2.4);
          }
          if (Math.abs(angleDelta) > 0.002) {
            cameraBus.orbit(angleDelta * 1.6, 0);
          }
          state.lastSpan = two.span;
          state.lastAngle = two.angleRad;
        }
      } else if (state.twoHandActive) {
        state.twoHandActive = false;
        state.lastSpan = null;
        state.lastAngle = null;
        send({ type: "TWO_HAND_END" });
      }

      // Push-to-return: both palms open and rushing toward the camera.
      if (two !== null && frame.bothPalmsOpen) {
        const scales = frame.hands.map((hand) => {
          const wrist = hand.landmarks[0];
          const middle = hand.landmarks[9];
          return wrist !== undefined && middle !== undefined
            ? Math.hypot(wrist.x - middle.x, wrist.y - middle.y)
            : 0.1;
        });
        const meanScale = (scales[0] ?? 0.1) + (scales[1] ?? 0.1);
        if (state.lastHandScale !== null) {
          const growth = meanScale / state.lastHandScale;
          if (growth > 1.06) {
            ui.setTimeline("live");
            setHoloActive(false);
            send({ type: "PUSH_BACK" });
          }
        }
        state.lastHandScale = meanScale;
      } else {
        state.lastHandScale = null;
      }

      if (first === undefined || two !== null) {
        return;
      }

      // Open-palm swipe: scrub time.
      if (first.palmOpen && Math.abs(first.velocity.x) > 0.9) {
        if (!state.scrubActive) {
          state.scrubActive = true;
          send({ type: "SCRUB_START" });
        }
        const world = useWorldStore.getState();
        if (world.timeOrigin !== null && world.lastFrameAt !== null) {
          const span = Math.max(1000, world.lastFrameAt - world.timeOrigin);
          const current =
            ui.timelineMode === "scrub" && ui.scrubTime !== null
              ? ui.scrubTime
              : world.lastFrameAt;
          const next = Math.min(
            world.lastFrameAt,
            Math.max(
              world.timeOrigin,
              current + first.velocity.x * span * 0.016,
            ),
          );
          if (next >= world.lastFrameAt - 200) {
            ui.setTimeline("live");
          } else {
            ui.setTimeline("scrub", next);
          }
        }
        return;
      }
      if (state.scrubActive && (!first.palmOpen || Math.abs(first.velocity.x) < 0.25)) {
        state.scrubActive = false;
        send({ type: "SCRUB_END" });
      }

      // Pointing: steer the reticle and highlight the nearest hologram.
      if (first.pointing) {
        const px = first.pointerTip.x * width;
        const py = first.pointerTip.y * height;
        const projected = projectEntities(width, height);
        let nearest: { id: string; d: number } | null = null;
        for (const item of projected) {
          const d = Math.hypot(item.x - px, item.y - py);
          if (d < 140 && (nearest === null || d < nearest.d)) {
            nearest = { id: item.id, d };
          }
        }
        state.hoverEntityId = nearest?.id ?? null;
      }

      // Pinch: select the highlighted object, or drag to orbit.
      if (first.pinched) {
        if (!state.pinchActive) {
          state.pinchActive = true;
          state.lastPinchCenter = first.center;
          send({ type: "PINCH_START" });
          if (state.hoverEntityId !== null) {
            ui.select(state.hoverEntityId);
            ui.requestFocus(state.hoverEntityId);
          }
        } else if (state.lastPinchCenter !== null) {
          const dx = first.center.x - state.lastPinchCenter.x;
          const dy = first.center.y - state.lastPinchCenter.y;
          cameraBus.orbit(dx * 3.4, dy * 2.2);
          state.lastPinchCenter = first.center;
        }
      } else if (state.pinchActive) {
        state.pinchActive = false;
        state.lastPinchCenter = null;
        send({ type: "PINCH_END" });
      }

      // Lone open palm at rest: expand memory for the highlighted object.
      if (
        first.palmOpen &&
        Math.abs(first.velocity.x) < 0.2 &&
        Math.abs(first.velocity.y) < 0.2 &&
        state.hoverEntityId !== null &&
        ui.selectedEntityId !== state.hoverEntityId
      ) {
        ui.select(state.hoverEntityId);
      }
    },
    [actor, send, setHoloActive],
  );

  // Detection + drawing loop.
  useEffect(() => {
    if (
      !holoActive ||
      trackerOutcome?.status !== "ready" ||
      webcamVideo === null
    ) {
      return;
    }
    const tracker = trackerOutcome.tracker;
    let raf = 0;
    let lastDetection = 0;

    const loop = () => {
      raf = requestAnimationFrame(loop);
      const canvas = canvasRef.current;
      if (canvas === null) {
        return;
      }
      const parent = canvas.parentElement;
      if (parent !== null) {
        const { clientWidth, clientHeight } = parent;
        if (canvas.width !== clientWidth || canvas.height !== clientHeight) {
          canvas.width = clientWidth;
          canvas.height = clientHeight;
        }
      }
      const now = performance.now();
      if (now - lastDetection > 33 && webcamVideo.readyState >= 2) {
        lastDetection = now;
        const rawHands = tracker.detect(webcamVideo, now);
        const frame = runtime.current.recognizer.update(rawHands, now);
        runtime.current.lastFrame = frame;
        setConfidence(
          frame.hands.length > 0
            ? frame.hands.reduce((sum, hand) => sum + hand.score, 0) /
                frame.hands.length
            : 0,
        );
        applyGestures(frame, canvas.width, canvas.height);
      }

      const context = canvas.getContext("2d");
      const frame = runtime.current.lastFrame;
      if (context === null) {
        return;
      }
      context.clearRect(0, 0, canvas.width, canvas.height);
      if (frame === null) {
        return;
      }
      for (const hand of frame.hands) {
        context.strokeStyle = hand.pinched
          ? palette.archive
          : `rgba(181, 242, 231, ${String(0.35 + hand.score * 0.45)})`;
        context.lineWidth = 1.6;
        context.beginPath();
        for (const [from, to] of HAND_LINKS) {
          const a = hand.landmarks[from];
          const b = hand.landmarks[to];
          if (a === undefined || b === undefined) {
            continue;
          }
          context.moveTo(a.x * canvas.width, a.y * canvas.height);
          context.lineTo(b.x * canvas.width, b.y * canvas.height);
        }
        context.stroke();
        for (const point of hand.landmarks) {
          context.fillStyle = "rgba(181, 242, 231, 0.7)";
          context.beginPath();
          context.arc(
            point.x * canvas.width,
            point.y * canvas.height,
            2,
            0,
            Math.PI * 2,
          );
          context.fill();
        }
        if (hand.pointing) {
          const tip = hand.pointerTip;
          context.strokeStyle = palette.lumen;
          context.lineWidth = 1.2;
          context.beginPath();
          context.arc(
            tip.x * canvas.width,
            tip.y * canvas.height,
            14,
            0,
            Math.PI * 2,
          );
          context.stroke();
          context.beginPath();
          context.arc(
            tip.x * canvas.width,
            tip.y * canvas.height,
            3,
            0,
            Math.PI * 2,
          );
          context.fillStyle = palette.lumen;
          context.fill();
        }
      }
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
    };
  }, [holoActive, trackerOutcome, webcamVideo, applyGestures]);

  const summonProgress = snapshot.context.summonProgress;
  const stateLabel = isActive ? `active · ${modeName}` : machineState;

  return (
    <>
      <button
        type="button"
        className={`holo-summon${holoActive ? " holo-summon--on" : ""}`}
        aria-pressed={holoActive}
        onClick={() => {
          setHoloActive(!holoActive);
        }}
        title="HoloConsole (H)"
      >
        <span className="holo-summon__ring" aria-hidden="true" />
        holo
      </button>

      <AnimatePresence>
        {holoActive && (
          <motion.div
            className="holo-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: reduced ? 0.1 : 0.4 }}
          >
            <canvas className="holo-overlay__canvas" ref={canvasRef} aria-hidden="true" />

            <motion.aside
              className="holo-hud"
              role="status"
              aria-label="HoloConsole state"
              initial={reduced ? { opacity: 0 } : { opacity: 0, y: 22, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={popSpring}
            >
              {liveStatus !== "live" || webcamVideo === null ? (
                <p className="holo-hud__notice">
                  HoloConsole needs a running webcam capture. Start the webcam
                  in the perception dock — or drive everything from the
                  keyboard (press ?).
                </p>
              ) : trackerOutcome === null ? (
                <p className="holo-hud__notice" aria-busy="true">
                  loading gesture runtime…
                </p>
              ) : trackerOutcome.status === "unavailable" ? (
                <p className="holo-hud__notice">{trackerOutcome.reason}</p>
              ) : (
                <>
                  <div className="holo-hud__state">
                    <AnimatePresence mode="wait" initial={false}>
                      <motion.span
                        key={stateLabel}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -8 }}
                        transition={microSwap}
                        className="holo-hud__state-label"
                      >
                        {stateLabel}
                      </motion.span>
                    </AnimatePresence>
                    <span
                      className="holo-hud__confidence"
                      title="Mean hand-tracking confidence"
                    >
                      conf {(confidence * 100).toFixed(0)}
                    </span>
                  </div>
                  {machineState === "summoning" && (
                    <div
                      className="holo-hud__summon"
                      role="progressbar"
                      aria-label="Summon hold"
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-valuenow={Math.round(summonProgress * 100)}
                    >
                      <span
                        className="holo-hud__summon-fill"
                        style={{ width: `${String(summonProgress * 100)}%` }}
                      />
                      <span className="holo-hud__summon-text">
                        hold both palms open…
                      </span>
                    </div>
                  )}
                  {machineState === "dormant" && (
                    <p className="holo-hud__notice">
                      show both open palms to summon
                    </p>
                  )}
                  <ul className="holo-hud__legend">
                    <li>point → aim · pinch → select / drag</li>
                    <li>two hands → spread, twist</li>
                    <li>open-palm swipe → scrub time</li>
                    <li>push both palms → return</li>
                  </ul>
                </>
              )}
              <button
                type="button"
                className="control-button control-button--ghosted control-button--small"
                onClick={() => {
                  send({ type: "CANCEL", reason: "operator cancel" });
                  setHoloActive(false);
                }}
              >
                cancel (esc)
              </button>
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
