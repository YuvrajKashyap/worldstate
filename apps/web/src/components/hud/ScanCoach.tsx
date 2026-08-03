/**
 * Active Scan Coach: explains where more evidence would help.
 * Directives are explicitly heuristic guidance over live quality metrics.
 */

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

import { adviseCoach, type CoachDirective } from "../../lib/coach/coach";
import { microSwap, settleSpring } from "../../lib/motion/presets";
import { useSessionStore } from "../../state/sessionStore";
import { useWorldStore } from "../../state/worldStore";

const ICONS: Record<CoachDirective["icon"], string> = {
  steady: "⊘",
  light: "☀",
  parallax: "⇄",
  revisit: "◎",
  closer: "⊕",
  done: "✓",
};

export function ScanCoach() {
  const reduced = useReducedMotion() ?? false;
  const liveStatus = useSessionStore((state) => state.liveStatus);
  const [directives, setDirectives] = useState<CoachDirective[]>([]);

  // Re-evaluate at a calm 1 Hz cadence, not per frame.
  useEffect(() => {
    if (liveStatus !== "live") {
      return;
    }
    const evaluate = () => {
      const world = useWorldStore.getState();
      setDirectives(
        adviseCoach({
          quality: world.telemetry.lastQuality,
          entities: world.entities,
          order: world.order,
          updatesPerSecond: world.telemetry.updatesPerSecond,
          nowMs: Date.now(),
        }),
      );
    };
    const lead = window.setTimeout(evaluate, 60);
    const timer = window.setInterval(evaluate, 1000);
    return () => {
      window.clearTimeout(lead);
      window.clearInterval(timer);
      setDirectives([]);
    };
  }, [liveStatus]);

  return (
    <div className="scan-coach" aria-live="polite" aria-label="Scan coach">
      <AnimatePresence mode="popLayout" initial={false}>
        {directives.map((directive) => (
          <motion.article
            key={directive.id}
            className={`scan-coach__card scan-coach__card--${directive.severity}`}
            initial={reduced ? { opacity: 0 } : { opacity: 0, y: 18, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={reduced ? { opacity: 0 } : { opacity: 0, y: -10, transition: microSwap }}
            transition={settleSpring}
            layout={!reduced}
          >
            <span className="scan-coach__icon" aria-hidden="true">
              {ICONS[directive.icon]}
            </span>
            <div>
              <h3 className="scan-coach__headline">{directive.headline}</h3>
              <p className="scan-coach__detail">{directive.detail}</p>
            </div>
          </motion.article>
        ))}
      </AnimatePresence>
    </div>
  );
}
