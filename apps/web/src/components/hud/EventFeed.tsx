/** Streaming change ledger: the latest world events, newest on top. */

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useMemo } from "react";

import { formatClock } from "../../lib/format";
import { popSpring } from "../../lib/motion/presets";
import { eventColor, eventGlyph } from "../../lib/palette";
import { useUiStore } from "../../state/uiStore";
import { useWorldStore } from "../../state/worldStore";

export function EventFeed() {
  const reduced = useReducedMotion() ?? false;
  const events = useWorldStore((state) => state.events);
  const entities = useWorldStore((state) => state.entities);
  const select = useUiStore((state) => state.select);
  const requestFocus = useUiStore((state) => state.requestFocus);

  const recent = useMemo(() => events.slice(-5).reverse(), [events]);

  if (recent.length === 0) {
    return null;
  }

  return (
    <section className="event-feed" aria-label="Recent changes">
      <AnimatePresence initial={false}>
        {recent.map((event) => {
          const label = entities[event.entity_id]?.label ?? "object";
          return (
            <motion.button
              key={event.id}
              type="button"
              className="event-feed__row"
              style={{ borderLeftColor: eventColor[event.kind] }}
              initial={reduced ? { opacity: 0 } : { opacity: 0, x: -26, scale: 0.96 }}
              animate={{ opacity: 1, x: 0, scale: 1 }}
              exit={{ opacity: 0, x: -12, transition: { duration: 0.16 } }}
              transition={popSpring}
              layout={!reduced}
              onClick={() => {
                select(event.entity_id);
                requestFocus(event.entity_id);
              }}
            >
              <span
                className="event-feed__glyph"
                style={{ color: eventColor[event.kind] }}
                aria-hidden="true"
              >
                {eventGlyph[event.kind]}
              </span>
              <span className="event-feed__body">
                <span className="event-feed__label">{label}</span>
                <span className="event-feed__kind">{event.kind}</span>
              </span>
              <time className="event-feed__time">
                {formatClock(Date.parse(event.occurred_at))}
              </time>
            </motion.button>
          );
        })}
      </AnimatePresence>
    </section>
  );
}
