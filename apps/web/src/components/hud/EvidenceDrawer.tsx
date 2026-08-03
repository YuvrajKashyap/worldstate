/**
 * Evidence Mode: every important claim traces to observations. Shows the
 * evidence references, timestamps, confidence trail, and model provenance
 * for the selected entity's recent events.
 */

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useMemo } from "react";

import { formatClock } from "../../lib/format";
import { drawerSpring } from "../../lib/motion/presets";
import { useSessionStore } from "../../state/sessionStore";
import { useUiStore } from "../../state/uiStore";
import { useWorldStore } from "../../state/worldStore";

export function EvidenceDrawer() {
  const reduced = useReducedMotion() ?? false;
  const open = useUiStore((state) => state.evidenceOpen);
  const setOpen = useUiStore((state) => state.setEvidenceOpen);
  const selectedEntityId = useUiStore((state) => state.selectedEntityId);
  const record = useWorldStore((state) =>
    selectedEntityId !== null ? state.entities[selectedEntityId] : undefined,
  );
  const events = useWorldStore((state) => state.events);
  const mode = useSessionStore((state) => state.mode);
  const providerMode = useSessionStore((state) => state.providerMode);

  const rows = useMemo(
    () =>
      selectedEntityId === null
        ? []
        : events
            .filter((event) => event.entity_id === selectedEntityId)
            .slice(-10)
            .reverse()
            .map((event) => ({
              id: event.id,
              kind: event.kind,
              at: Date.parse(event.occurred_at),
              confidence: event.confidence,
              evidence: event.evidence_ids,
            })),
    [events, selectedEntityId],
  );

  return (
    <AnimatePresence>
      {open && record !== undefined && (
        <motion.section
          className="evidence-drawer"
          role="dialog"
          aria-label={`Evidence for ${record.label}`}
          initial={reduced ? { opacity: 0 } : { y: "104%" }}
          animate={reduced ? { opacity: 1 } : { y: 0 }}
          exit={reduced ? { opacity: 0 } : { y: "104%" }}
          transition={drawerSpring}
        >
          <header className="evidence-drawer__header">
            <h2 className="evidence-drawer__title">
              evidence · {record.label}
            </h2>
            <button
              type="button"
              className="icon-button"
              onClick={() => {
                setOpen(false);
              }}
              title="Close evidence"
            >
              ✕
            </button>
          </header>

          <div className="evidence-drawer__grid">
            <section aria-label="Event evidence">
              <h3 className="memory-panel__subheading">event trail</h3>
              <ul className="evidence-list">
                {rows.length === 0 && (
                  <li className="panel-footnote">No recorded events yet.</li>
                )}
                {rows.map((row) => (
                  <li key={row.id} className="evidence-list__row">
                    <span className="evidence-list__kind">{row.kind}</span>
                    <time className="evidence-list__time">
                      {formatClock(row.at)}
                    </time>
                    <span className="evidence-list__confidence">
                      c {(row.confidence * 100).toFixed(0)}
                    </span>
                    <span className="evidence-list__ids">
                      {row.evidence.length > 0
                        ? row.evidence.map((id) => id.slice(-8)).join(" · ")
                        : "no frames retained"}
                    </span>
                  </li>
                ))}
              </ul>
            </section>

            <section aria-label="Provenance">
              <h3 className="memory-panel__subheading">provenance</h3>
              <dl className="provenance">
                <div>
                  <dt>provider mode</dt>
                  <dd>{providerMode ?? "unknown"}</dd>
                </div>
                <div>
                  <dt>source</dt>
                  <dd>
                    {mode === "simulation"
                      ? "client-side deterministic simulation"
                      : "local perception adapters (worldstate backend)"}
                  </dd>
                </div>
                <div>
                  <dt>calibration</dt>
                  <dd>
                    raw scores; no calibration experiment has been applied
                  </dd>
                </div>
                <div>
                  <dt>coordinate frame</dt>
                  <dd>worldstate_scene_v1 · meters</dd>
                </div>
              </dl>
              <p className="panel-footnote">
                Predictions are never presented as direct observations
                (EVT-004). Missing evidence is shown as missing.
              </p>
            </section>
          </div>
        </motion.section>
      )}
    </AnimatePresence>
  );
}
