/**
 * Perception dock: the live capture preview with detection overlays.
 * Draws the exact encoded frame (so boxes always align), bracket-style
 * detections in presence colors, and the capture-quality readout.
 */

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";

import { presenceColor } from "../../lib/palette";
import { gravitationalEase, microSwap } from "../../lib/motion/presets";
import {
  MAX_OBJECT_PROMPTS,
  parseObjectPrompts,
} from "../../lib/live/prompts";
import { fitWithin } from "../../lib/live/frames";
import {
  estimateMotion,
  projectBox,
  type MotionEstimate,
} from "../../lib/world/prediction";
import { useSessionStore, type SourceKind } from "../../state/sessionStore";
import { useUiStore } from "../../state/uiStore";
import {
  useWorldStore,
  type EntitySnapshot,
} from "../../state/worldStore";

export function VideoDock() {
  const reduced = useReducedMotion() ?? false;
  const liveStatus = useSessionStore((state) => state.liveStatus);
  const liveError = useSessionStore((state) => state.liveError);
  const sourceKind = useSessionStore((state) => state.sourceKind);
  const previewCanvas = useSessionStore((state) => state.previewCanvas);
  const webcamVideo = useSessionStore((state) => state.webcamVideo);
  const startLive = useSessionStore((state) => state.startLive);
  const stopLive = useSessionStore((state) => state.stopLive);
  const mode = useSessionStore((state) => state.mode);
  const canMutate = useSessionStore((state) => state.canMutate);
  const objectPrompts = useSessionStore((state) => state.objectPrompts);
  const setObjectPrompts = useSessionStore((state) => state.setObjectPrompts);
  const quality = useWorldStore((state) => state.telemetry.lastQuality);
  const scrubbing = useUiStore((state) => state.timelineMode === "scrub");

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const motionCache = useRef(
    new Map<
      string,
      { history: EntitySnapshot[]; estimate: MotionEstimate | null }
    >(),
  );
  const [collapsed, setCollapsed] = useState(false);
  const [targetDraft, setTargetDraft] = useState(() => objectPrompts.join(", "));

  const drawOverlay = useCallback(() => {
    const canvas = canvasRef.current;
    if (canvas === null || (previewCanvas === null && webcamVideo === null)) {
      return;
    }
    const context = canvas.getContext("2d");
    if (context === null) {
      return;
    }
    const webcamReady =
      webcamVideo !== null &&
      webcamVideo.readyState >= HTMLMediaElement.HAVE_CURRENT_DATA &&
      webcamVideo.videoWidth > 0 &&
      webcamVideo.videoHeight > 0;
    const size = webcamReady
      ? fitWithin(webcamVideo.videoWidth, webcamVideo.videoHeight, 640, 360)
      : previewCanvas === null
        ? null
        : { width: previewCanvas.width, height: previewCanvas.height };
    if (size === null) {
      return;
    }
    if (canvas.width !== size.width || canvas.height !== size.height) {
      canvas.width = size.width;
      canvas.height = size.height;
    }
    if (webcamReady) {
      // The camera preview is intentionally independent of inference. It can
      // render at the display refresh rate while results arrive at their own
      // bounded cadence.
      context.drawImage(webcamVideo, 0, 0, size.width, size.height);
    } else if (previewCanvas !== null) {
      context.drawImage(previewCanvas, 0, 0);
    }

    const { entities, order } = useWorldStore.getState();
    const now = Date.now();
    context.lineWidth = Math.max(1.5, canvas.width / 480);
    context.font = `${String(Math.max(11, canvas.width / 52))}px "JetBrains Mono Variable", monospace`;
    for (const id of order) {
      const record = entities[id];
      if (record === undefined) {
        continue;
      }
      if (record.presence === "missing" || record.presence === "archived") {
        continue;
      }
      const cached = motionCache.current.get(id);
      const estimate =
        cached?.history === record.history
          ? cached.estimate
          : estimateMotion(record.history);
      if (cached?.history !== record.history) {
        motionCache.current.set(id, { history: record.history, estimate });
      }
      const predicted = projectBox(
        record.box,
        estimate?.boxVelocity ?? null,
        estimate?.observedAt ?? record.lastSeenAt,
        now,
      );
      const x1 = Math.max(0, Math.min(canvas.width, predicted[0]));
      const y1 = Math.max(0, Math.min(canvas.height, predicted[1]));
      const x2 = Math.max(x1, Math.min(canvas.width, predicted[2]));
      const y2 = Math.max(y1, Math.min(canvas.height, predicted[3]));
      const color = presenceColor[record.presence];
      const width = x2 - x1;
      const height = y2 - y1;
      const arm = Math.min(18, width * 0.24);
      context.strokeStyle = color;
      context.setLineDash(record.presence === "occluded" ? [6, 5] : []);
      // Corner brackets rather than full boxes: reads as instrumentation.
      context.beginPath();
      for (const [cx, cy, dx, dy] of [
        [x1, y1, 1, 1],
        [x2, y1, -1, 1],
        [x1, y2, 1, -1],
        [x2, y2, -1, -1],
      ] as const) {
        context.moveTo(cx + dx * arm, cy);
        context.lineTo(cx, cy);
        context.lineTo(cx, cy + dy * arm);
      }
      context.stroke();
      context.setLineDash([]);
      context.fillStyle = color;
      context.fillText(
        `${record.label} ${(record.confidence * 100).toFixed(0)}`,
        x1 + 3,
        Math.max(12, y1 - 6),
      );
      void height;
    }
  }, [previewCanvas, webcamVideo]);

  useEffect(() => {
    if ((previewCanvas === null && webcamVideo === null) || collapsed) {
      return;
    }
    let raf = 0;
    const loop = () => {
      drawOverlay();
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(raf);
    };
  }, [previewCanvas, webcamVideo, drawOverlay, collapsed]);

  const busy = liveStatus === "starting" || liveStatus === "stopping";
  const start = (source: SourceKind) => {
    if (source === "webcam") {
      const prompts = parseObjectPrompts(targetDraft);
      if (prompts.length > 0) {
        setObjectPrompts(prompts);
      }
    }
    void startLive(source);
  };

  const keyframeScore = quality.keyframe_score ?? null;
  const canStart = mode === "simulation" || canMutate;
  const targetCount = parseObjectPrompts(targetDraft).length;

  return (
    <motion.section
      className={`video-dock${collapsed ? " video-dock--collapsed" : ""}${scrubbing ? " video-dock--dimmed" : ""}`}
      aria-label="Live capture"
      initial={reduced ? false : { opacity: 0, y: 28, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.8, ease: gravitationalEase, delay: 0.45 }}
    >
      <header className="video-dock__bar">
        <span className="video-dock__title">
          perception
          {liveStatus === "live" && (
            <span className="video-dock__rec" aria-hidden="true" />
          )}
        </span>
        {keyframeScore !== null && liveStatus === "live" && (
          <span className="video-dock__quality" title="Keyframe quality score">
            kf {(keyframeScore * 100).toFixed(0)}
          </span>
        )}
        <button
          type="button"
          className="video-dock__collapse"
          onClick={() => {
            setCollapsed((value) => !value);
          }}
          aria-expanded={!collapsed}
        >
          {collapsed ? "expand" : "collapse"}
        </button>
      </header>

      {!collapsed && (
        <div className="video-dock__stage">
          {webcamVideo !== null ||
          (liveStatus === "live" && previewCanvas !== null) ? (
            <>
              <canvas
                ref={canvasRef}
                className="video-dock__canvas"
                aria-label={
                  sourceKind === "webcam"
                    ? "Webcam preview with detections"
                    : "Synthetic desk preview with detections"
                }
              />
              <span className="video-dock__scanline" aria-hidden="true" />
            </>
          ) : (
            <div className="video-dock__idle">
              <AnimatePresence mode="wait" initial={false}>
                <motion.div
                  key={liveStatus + (liveError ?? "")}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={microSwap}
                  className="video-dock__idle-copy"
                >
                  {liveStatus === "error" ? (
                    <p className="video-dock__error" role="alert">
                      {liveError}
                    </p>
                  ) : busy ? (
                    <p role="status">
                      {sourceKind === "webcam"
                        ? "starting camera and learned perception…"
                        : "starting isolated simulation…"}
                    </p>
                  ) : !canStart ? (
                    <p>
                      Read-only session: relaunch WorldState to enable capture,
                      or use simulation.
                    </p>
                  ) : (
                    <p>Camera is off. Nothing is captured until you begin.</p>
                  )}
                </motion.div>
              </AnimatePresence>
            </div>
          )}
        </div>
      )}

      {!collapsed && liveStatus !== "live" && mode === "backend" && (
        <label className="video-dock__targets">
          <span>
            webcam targets
            <output>{targetCount}/{MAX_OBJECT_PROMPTS}</output>
          </span>
          <textarea
            value={targetDraft}
            rows={2}
            disabled={busy}
            onChange={(event) => {
              setTargetDraft(event.target.value);
            }}
            onBlur={() => {
              const prompts = parseObjectPrompts(targetDraft);
              if (prompts.length > 0) {
                setObjectPrompts(prompts);
                setTargetDraft(prompts.join(", "));
              }
            }}
            aria-describedby="webcam-target-help"
          />
          <small id="webcam-target-help">
            Grounding DINO names these categories and also searches for salient
            unlisted items as unknown objects. Tracking stays real-time between
            discovery passes.
          </small>
        </label>
      )}

      <footer className="video-dock__controls">
        {liveStatus === "live" ? (
          <button
            type="button"
            className="control-button control-button--stop"
            onClick={() => {
              void stopLive();
            }}
          >
            stop capture
          </button>
        ) : (
          mode === "simulation" ? (
            <button
              type="button"
              className="control-button"
              disabled={busy}
              onClick={() => {
                start("synthetic");
              }}
            >
              start isolated simulation
            </button>
          ) : (
            <>
              <button
                type="button"
                className="control-button"
                disabled={busy || !canStart || targetCount === 0}
                onClick={() => {
                  start("webcam");
                }}
              >
                start webcam
              </button>
              <details className="video-dock__demo-controls">
                <summary>developer demo</summary>
                <button
                  type="button"
                  className="control-button control-button--ghosted"
                  disabled={busy || !canStart}
                  onClick={() => {
                    start("synthetic");
                  }}
                  title="Isolated deterministic replay — no camera required"
                >
                  run synthetic replay
                </button>
              </details>
            </>
          )
        )}
      </footer>
    </motion.section>
  );
}
