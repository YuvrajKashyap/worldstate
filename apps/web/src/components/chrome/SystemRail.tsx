/**
 * Left instrument rail: capability lamps, live telemetry, view layers,
 * and the X-ray presence legend. Values come straight from /api/v1/system
 * and frame metrics; raw confidences are labeled uncalibrated.
 */

import { motion, useReducedMotion } from "motion/react";

import { formatMs, percentile } from "../../lib/format";
import { gravitationalEase } from "../../lib/motion/presets";
import { presenceColor } from "../../lib/palette";
import { useSessionStore } from "../../state/sessionStore";
import { useUiStore, type ViewLayers } from "../../state/uiStore";
import { useWorldStore } from "../../state/worldStore";
import { Sparkline } from "./Sparkline";

const LAYER_LABELS: Record<keyof ViewLayers, string> = {
  ghosts: "Ghost mode",
  graph: "Scene graph",
  uncertainty: "Uncertainty",
  labels: "Labels",
};

const LAYER_KEYS: Record<keyof ViewLayers, string> = {
  ghosts: "G",
  graph: "R",
  uncertainty: "U",
  labels: "L",
};

const PRESENCE_LEGEND = [
  { key: "visible", text: "solid — observed now" },
  { key: "occluded", text: "wireframe — occluded" },
  { key: "predicted", text: "amber pulse — predicted" },
  { key: "missing", text: "red ghost — missing" },
  { key: "archived", text: "faded — stale memory" },
] as const;

export function SystemRail() {
  const reduced = useReducedMotion() ?? false;
  const system = useSessionStore((state) => state.system);
  const mode = useSessionStore((state) => state.mode);
  const telemetry = useWorldStore((state) => state.telemetry);
  const layers = useUiStore((state) => state.layers);
  const toggleLayer = useUiStore((state) => state.toggleLayer);

  const p95 = percentile(telemetry.latencyMs, 0.95);
  const p50 = percentile(telemetry.latencyMs, 0.5);
  const inferenceP95 = percentile(telemetry.inferenceMs, 0.95);
  const inferenceP50 = percentile(telemetry.inferenceMs, 0.5);
  const encodeP95 = percentile(telemetry.encodeMs, 0.95);
  const encodeP50 = percentile(telemetry.encodeMs, 0.5);
  const resumeP95 = percentile(telemetry.resultToCaptureMs, 0.95);
  const resumeP50 = percentile(telemetry.resultToCaptureMs, 0.5);

  const capabilities =
    mode === "simulation"
      ? { simulation: "ready" as const }
      : (system?.capabilities ?? {});

  return (
    <motion.aside
      className="system-rail"
      aria-label="System status and view controls"
      initial={reduced ? false : { opacity: 0, x: -18 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.7, ease: gravitationalEase, delay: 0.25 }}
    >
      <section className="rail-block" aria-label="Capabilities">
        <h2 className="rail-heading">Capabilities</h2>
        <ul className="capability-list">
          {Object.entries(capabilities).map(([name, state]) => (
            <li key={name} className={`capability capability--${state}`}>
              <span className="capability__lamp" aria-hidden="true" />
              <span className="capability__name">{name.replace(/_/g, " ")}</span>
              <span className="capability__state">{state}</span>
            </li>
          ))}
          {Object.keys(capabilities).length === 0 && (
            <li className="capability capability--unavailable">
              <span className="capability__lamp" aria-hidden="true" />
              <span className="capability__name">no link</span>
            </li>
          )}
        </ul>
      </section>

      <section className="rail-block" aria-label="Live telemetry">
        <h2 className="rail-heading">Telemetry</h2>
        <dl className="telemetry">
          <div className="telemetry__row">
            <dt>capture → result</dt>
            <dd>
              <Sparkline
                values={telemetry.latencyMs.slice(-48)}
                label="Capture to result latency trend"
              />
              <span className="telemetry__value">
                {formatMs(p50)}
                <span className="telemetry__sub"> p95 {formatMs(p95)}</span>
              </span>
            </dd>
          </div>
          <div className="telemetry__row">
            <dt>provider inference</dt>
            <dd>
              <span className="telemetry__value">
                {formatMs(inferenceP50)}
                <span className="telemetry__sub">
                  {" "}p95 {formatMs(inferenceP95)}
                </span>
              </span>
            </dd>
          </div>
          <div className="telemetry__row">
            <dt>browser frame pack</dt>
            <dd>
              <span className="telemetry__value">
                {formatMs(encodeP50)}
                <span className="telemetry__sub">
                  {" "}p95 {formatMs(encodeP95)}
                </span>
              </span>
            </dd>
          </div>
          <div className="telemetry__row">
            <dt>result → next capture</dt>
            <dd>
              <span className="telemetry__value">
                {formatMs(resumeP50)}
                <span className="telemetry__sub">
                  {" "}p95 {formatMs(resumeP95)}
                </span>
              </span>
            </dd>
          </div>
          <div className="telemetry__row">
            <dt>updates / s</dt>
            <dd>
              <span className="telemetry__value">
                {telemetry.updatesPerSecond.toFixed(1)}
              </span>
            </dd>
          </div>
          <div className="telemetry__row">
            <dt>dropped · skipped</dt>
            <dd>
              <span className="telemetry__value">
                {telemetry.droppedFrames} · {telemetry.skippedIntervals}
              </span>
            </dd>
          </div>
        </dl>
        <p className="rail-footnote">
          scores and monocular depth are uncalibrated
        </p>
      </section>

      <section className="rail-block" aria-label="View layers">
        <h2 className="rail-heading">Layers</h2>
        <div className="layer-toggles">
          {(Object.keys(LAYER_LABELS) as (keyof ViewLayers)[]).map((key) => (
            <button
              key={key}
              type="button"
              className="layer-toggle"
              aria-pressed={layers[key]}
              onClick={() => {
                toggleLayer(key);
              }}
            >
              <span className="layer-toggle__key" aria-hidden="true">
                {LAYER_KEYS[key]}
              </span>
              {LAYER_LABELS[key]}
              <span
                className={`layer-toggle__lamp${layers[key] ? " layer-toggle__lamp--on" : ""}`}
                aria-hidden="true"
              />
            </button>
          ))}
        </div>
      </section>

      <section className="rail-block rail-block--legend" aria-label="Presence grammar">
        <h2 className="rail-heading">X-ray grammar</h2>
        <ul className="legend">
          {PRESENCE_LEGEND.map((item) => (
            <li key={item.key} className="legend__row">
              <span
                className="legend__swatch"
                style={{ color: presenceColor[item.key] }}
                aria-hidden="true"
              />
              {item.text}
            </li>
          ))}
        </ul>
      </section>
    </motion.aside>
  );
}
