/**
 * Accessible parallel object list: every remembered entity as a real
 * focusable control mirroring the canvas (UI-003, accessibility spec §15).
 */

import { motion, useReducedMotion } from "motion/react";

import { formatAgo } from "../../lib/format";
import { gravitationalEase } from "../../lib/motion/presets";
import { presenceColor, presenceLabel } from "../../lib/palette";
import { useUiStore } from "../../state/uiStore";
import { useWorldStore } from "../../state/worldStore";

export function EntityDock() {
  const reduced = useReducedMotion() ?? false;
  const order = useWorldStore((state) => state.order);
  const entities = useWorldStore((state) => state.entities);
  const selectedEntityId = useUiStore((state) => state.selectedEntityId);
  const select = useUiStore((state) => state.select);
  const requestFocus = useUiStore((state) => state.requestFocus);

  if (order.length === 0) {
    return null;
  }

  return (
    <motion.nav
      className="entity-dock"
      aria-label="Remembered objects"
      initial={reduced ? false : { opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.6, ease: gravitationalEase, delay: 0.5 }}
    >
      <ul className="entity-dock__list">
        {order.map((id) => {
          const record = entities[id];
          if (record === undefined) {
            return null;
          }
          const selected = id === selectedEntityId;
          return (
            <li key={id}>
              <button
                type="button"
                className={`entity-chip${selected ? " entity-chip--selected" : ""}`}
                aria-pressed={selected}
                aria-label={`${record.label}: ${presenceLabel[record.presence]}${
                  record.lastVisibleAt !== null
                    ? `, last visible ${formatAgo(record.lastVisibleAt)}`
                    : ""
                }`}
                onClick={() => {
                  select(selected ? null : id);
                  if (!selected) {
                    requestFocus(id);
                  }
                }}
              >
                <span
                  className={`entity-chip__lamp entity-chip__lamp--${record.presence}`}
                  style={{ background: presenceColor[record.presence] }}
                  aria-hidden="true"
                />
                <span className="entity-chip__label">{record.label}</span>
                <span className="entity-chip__state">
                  {presenceLabel[record.presence]}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </motion.nav>
  );
}
