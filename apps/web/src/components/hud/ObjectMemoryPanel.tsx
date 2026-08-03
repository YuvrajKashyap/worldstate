/**
 * Object Memory: the contextual dossier for a selected entity —
 * lifecycle position, confidence trace, movement trail, events, and
 * evidence references. Appears contextually; never permanently occupies
 * the viewport.
 */

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useMemo, useState } from "react";

import { formatAgo, formatClock } from "../../lib/format";
import { drawerSpring } from "../../lib/motion/presets";
import { eventGlyph, presenceColor, presenceLabel } from "../../lib/palette";
import type { Presence } from "../../lib/protocol/messages";
import { useSessionStore } from "../../state/sessionStore";
import { useUiStore } from "../../state/uiStore";
import { useWorldStore } from "../../state/worldStore";
import { Sparkline } from "../chrome/Sparkline";

const LIFECYCLE: Presence[] = [
  "visible",
  "occluded",
  "predicted",
  "missing",
  "rediscovered",
  "archived",
];

function MovementTrail({
  points,
}: {
  points: { x: number; z: number; presence: Presence }[];
}) {
  if (points.length < 2) {
    return (
      <p className="panel-footnote">Not enough movement recorded yet.</p>
    );
  }
  const xs = points.map((point) => point.x);
  const zs = points.map((point) => point.z);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minZ = Math.min(...zs);
  const maxZ = Math.max(...zs);
  const spanX = Math.max(0.2, maxX - minX);
  const spanZ = Math.max(0.2, maxZ - minZ);
  const width = 220;
  const height = 96;
  const project = (point: { x: number; z: number }) => ({
    x: 10 + ((point.x - minX) / spanX) * (width - 20),
    y: 10 + ((point.z - minZ) / spanZ) * (height - 20),
  });
  const path = points
    .map((point, index) => {
      const { x, y } = project(point);
      return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const last = project(points[points.length - 1] ?? { x: 0, z: 0 });
  return (
    <svg
      viewBox={`0 0 ${String(width)} ${String(height)}`}
      className="movement-trail"
      role="img"
      aria-label="Top-down movement trail"
    >
      <path d={path} fill="none" stroke="var(--memory)" strokeWidth="1.4" opacity="0.8" />
      <circle cx={last.x} cy={last.y} r="3.2" fill="var(--lumen)" />
    </svg>
  );
}

export function ObjectMemoryPanel() {
  const reduced = useReducedMotion() ?? false;
  const selectedEntityId = useUiStore((state) => state.selectedEntityId);
  const select = useUiStore((state) => state.select);
  const togglePin = useUiStore((state) => state.togglePin);
  const toggleHidden = useUiStore((state) => state.toggleHidden);
  const requestFocus = useUiStore((state) => state.requestFocus);
  const setEvidenceOpen = useUiStore((state) => state.setEvidenceOpen);
  const pinned = useUiStore((state) =>
    state.selectedEntityId !== null
      ? state.pinnedEntityIds.includes(state.selectedEntityId)
      : false,
  );
  const hidden = useUiStore((state) =>
    state.selectedEntityId !== null
      ? state.hiddenEntityIds.includes(state.selectedEntityId)
      : false,
  );
  const record = useWorldStore((state) =>
    selectedEntityId !== null ? state.entities[selectedEntityId] : undefined,
  );
  const events = useWorldStore((state) => state.events);
  const submitCommand = useSessionStore((state) => state.submitCommand);
  const sceneId = useSessionStore((state) => state.sceneId);
  const mode = useSessionStore((state) => state.mode);
  const [lastSeenReport, setLastSeenReport] = useState<string | null>(null);

  const entityEvents = useMemo(
    () =>
      selectedEntityId === null
        ? []
        : events
            .filter((event) => event.entity_id === selectedEntityId)
            .slice(-6)
            .reverse(),
    [events, selectedEntityId],
  );

  const confidenceTrace = useMemo(
    () => record?.history.map((sample) => sample.confidence) ?? [],
    [record],
  );

  const trail = useMemo(
    () =>
      (record?.history ?? [])
        .filter((sample) => sample.position !== null)
        .filter((_, index, list) => index % Math.ceil(list.length / 60) === 0)
        .map((sample) => ({
          x: sample.position?.[0] ?? 0,
          z: sample.position?.[2] ?? 0,
          presence: sample.presence,
        })),
    [record],
  );

  const evidenceIds = useMemo(() => {
    const ids = new Set<string>();
    for (const event of entityEvents) {
      for (const id of event.evidence_ids) {
        ids.add(id);
      }
    }
    return [...ids];
  }, [entityEvents]);

  const findLastSeen = () => {
    if (selectedEntityId === null || sceneId === null || record === undefined) {
      return;
    }
    void submitCommand({
      command: "find_last_seen",
      sceneId,
      entityId: selectedEntityId,
    }).then((result) => {
      if (result?.status !== "completed") {
        setLastSeenReport("The command channel did not answer.");
        return;
      }
      const payload = result.result ?? {};
      const lastSeenAt =
        typeof payload.last_seen_at === "string" ? payload.last_seen_at : null;
      const position = Array.isArray(payload.position_m)
        ? (payload.position_m as number[])
        : null;
      const positionText =
        position?.length === 3
          ? ` at [${position.map((v) => v.toFixed(2)).join(", ")}] m`
          : "";
      setLastSeenReport(
        lastSeenAt !== null
          ? `Last observed ${formatAgo(Date.parse(lastSeenAt))}${positionText}. ${
              record.presence === "visible" ? "Currently present." : "Not currently observed."
            }`
          : "Never directly observed.",
      );
      requestFocus(selectedEntityId);
    });
  };

  return (
    <AnimatePresence>
      {record !== undefined && selectedEntityId !== null && (
        <motion.aside
          key={selectedEntityId}
          className="memory-panel"
          aria-label={`Object memory for ${record.label}`}
          initial={reduced ? { opacity: 0 } : { x: 380, opacity: 0.4 }}
          animate={reduced ? { opacity: 1 } : { x: 0, opacity: 1 }}
          exit={reduced ? { opacity: 0 } : { x: 380, opacity: 0 }}
          transition={drawerSpring}
        >
          <header className="memory-panel__header">
            <div>
              <h2 className="memory-panel__title">{record.label}</h2>
              <p
                className="memory-panel__presence"
                style={{ color: presenceColor[record.presence] }}
              >
                <span
                  className={`presence-lamp presence-lamp--${record.presence}`}
                  aria-hidden="true"
                />
                {presenceLabel[record.presence]}
              </p>
            </div>
            <div className="memory-panel__tools">
              <button
                type="button"
                className="icon-button"
                aria-pressed={pinned}
                title={pinned ? "Unpin" : "Pin"}
                onClick={() => {
                  togglePin(selectedEntityId);
                }}
              >
                ◈
              </button>
              <button
                type="button"
                className="icon-button"
                aria-pressed={hidden}
                title={hidden ? "Show in world" : "Hide from world"}
                onClick={() => {
                  toggleHidden(selectedEntityId);
                }}
              >
                ◌
              </button>
              <button
                type="button"
                className="icon-button"
                title="Close"
                onClick={() => {
                  select(null);
                }}
              >
                ✕
              </button>
            </div>
          </header>

          <ol className="lifecycle" aria-label="Presence lifecycle">
            {LIFECYCLE.map((stage) => (
              <li
                key={stage}
                className={`lifecycle__stage${stage === record.presence ? " lifecycle__stage--current" : ""}`}
                style={
                  stage === record.presence
                    ? { color: presenceColor[stage] }
                    : undefined
                }
              >
                {stage}
              </li>
            ))}
          </ol>

          <dl className="memory-facts">
            <div>
              <dt>confidence</dt>
              <dd>
                <Sparkline
                  values={confidenceTrace.slice(-64)}
                  label="Confidence over time"
                  stroke={presenceColor[record.presence]}
                />
                <span className="memory-facts__value">
                  {(record.confidence * 100).toFixed(0)}
                  <span className="memory-facts__unit"> raw</span>
                </span>
              </dd>
            </div>
            <div>
              <dt>uncertainty</dt>
              <dd>
                <span
                  className="uncertainty-bar"
                  role="img"
                  aria-label={`Uncertainty ${(record.uncertainty * 100).toFixed(0)} percent`}
                >
                  <span
                    className="uncertainty-bar__fill"
                    style={{ width: `${String(record.uncertainty * 100)}%` }}
                  />
                </span>
                <span className="memory-facts__value">
                  {(record.uncertainty * 100).toFixed(0)}%
                </span>
              </dd>
            </div>
            <div>
              <dt>position</dt>
              <dd className="memory-facts__mono">
                {record.position !== null
                  ? `[${record.position.map((v) => v.toFixed(2)).join(", ")}] m`
                  : "unknown"}
              </dd>
            </div>
            <div>
              <dt>first observed</dt>
              <dd className="memory-facts__mono">{formatClock(record.firstSeenAt)}</dd>
            </div>
            <div>
              <dt>last visible</dt>
              <dd className="memory-facts__mono">
                {record.lastVisibleAt !== null
                  ? formatAgo(record.lastVisibleAt)
                  : "never"}
              </dd>
            </div>
          </dl>

          <section aria-label="Movement history">
            <h3 className="memory-panel__subheading">movement</h3>
            <MovementTrail points={trail} />
          </section>

          <section aria-label="Recent events">
            <h3 className="memory-panel__subheading">events</h3>
            <ul className="event-ledger">
              {entityEvents.length === 0 && (
                <li className="panel-footnote">No changes recorded yet.</li>
              )}
              {entityEvents.map((event) => (
                <li key={event.id} className="event-ledger__row">
                  <span
                    className="event-ledger__glyph"
                    style={{ color: presenceColor.visible }}
                    aria-hidden="true"
                  >
                    {eventGlyph[event.kind]}
                  </span>
                  <span className="event-ledger__kind">{event.kind}</span>
                  <time className="event-ledger__time">
                    {formatClock(Date.parse(event.occurred_at))}
                  </time>
                </li>
              ))}
            </ul>
          </section>

          {lastSeenReport !== null && (
            <p className="memory-panel__report" role="status">
              {lastSeenReport}
            </p>
          )}

          <footer className="memory-panel__actions">
            <button type="button" className="control-button" onClick={findLastSeen}>
              find last seen
            </button>
            <button
              type="button"
              className="control-button control-button--ghosted"
              onClick={() => {
                requestFocus(selectedEntityId);
              }}
            >
              focus camera
            </button>
            <button
              type="button"
              className="control-button control-button--ghosted"
              disabled={evidenceIds.length === 0}
              onClick={() => {
                setEvidenceOpen(true);
              }}
            >
              evidence ({evidenceIds.length})
            </button>
          </footer>
          <p className="panel-footnote">
            {mode === "simulation"
              ? "Simulated memory — deterministic desk-change replay."
              : "Provenance: live perception via typed provider adapters."}
          </p>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
