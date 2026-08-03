/**
 * Boot + connection gate. Types the system check log, resolves the
 * backend link (fragment bootstrap → cookie session), and offers the
 * labeled simulation when no backend is reachable. The world powers on
 * behind it; this overlay lifts like a letterbox when ready.
 */

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useState } from "react";

import { gravitationalEase } from "../../lib/motion/presets";
import { useSessionStore } from "../../state/sessionStore";

type BootLine = { text: string; tone: "normal" | "ok" | "warn" };

function useBootLines(): BootLine[] {
  const backendStatus = useSessionStore((state) => state.backendStatus);
  const authenticated = useSessionStore((state) => state.authenticated);
  const system = useSessionStore((state) => state.system);
  const bootstrapMessage = useSessionStore((state) => state.bootstrapMessage);

  return useMemo(() => {
    const lines: BootLine[] = [
      { text: "worldstate interface v1 — spatial memory console", tone: "normal" },
      { text: "checking local backend at loopback…", tone: "normal" },
    ];
    if (backendStatus === "probing") {
      return lines;
    }
    if (backendStatus === "unreachable") {
      lines.push({ text: "backend: unreachable", tone: "warn" });
      lines.push({
        text: "the interface can run a deterministic simulation instead",
        tone: "normal",
      });
      return lines;
    }
    lines.push({
      text: `backend: online · provider ${system?.provider_mode ?? "?"} · ${system?.environment ?? ""}`,
      tone: "ok",
    });
    if (bootstrapMessage !== null) {
      lines.push({ text: `bootstrap: ${bootstrapMessage}`, tone: "warn" });
    }
    if (authenticated) {
      lines.push({ text: "session: established (cookie + csrf)", tone: "ok" });
    } else {
      lines.push({
        text: "session: none — launch WorldState to mint a link token",
        tone: "warn",
      });
    }
    return lines;
  }, [backendStatus, authenticated, system, bootstrapMessage]);
}

function TypedLine({
  line,
  delay,
  reduced,
}: {
  line: BootLine;
  delay: number;
  reduced: boolean;
}) {
  return (
    <motion.p
      className={`boot-line boot-line--${line.tone}`}
      initial={reduced ? { opacity: 1 } : { opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.25, delay }}
    >
      <motion.span
        className="boot-line__mask"
        initial={reduced ? { width: "100%" } : { width: "0%" }}
        animate={{ width: "100%" }}
        transition={{ duration: reduced ? 0 : 0.5, delay, ease: "linear" }}
      >
        {line.text}
      </motion.span>
    </motion.p>
  );
}

export function ConnectGate() {
  const reduced = useReducedMotion() ?? false;
  const backendStatus = useSessionStore((state) => state.backendStatus);
  const authenticated = useSessionStore((state) => state.authenticated);
  const mode = useSessionStore((state) => state.mode);
  const enterSimulation = useSessionStore((state) => state.enterSimulation);
  const initialize = useSessionStore((state) => state.initialize);
  const lines = useBootLines();
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    void initialize();
  }, [initialize]);

  // Auto-lift once a working mode exists, after the log settles.
  useEffect(() => {
    if (mode === null) {
      return;
    }
    const timer = window.setTimeout(
      () => {
        setDismissed(true);
      },
      reduced ? 150 : 1_600,
    );
    return () => {
      window.clearTimeout(timer);
    };
  }, [mode, reduced]);

  const resolved = backendStatus !== "probing";
  const needsChoice = resolved && mode === null;

  return (
    <AnimatePresence>
      {!dismissed && (
        <motion.div
          className="connect-gate"
          role={needsChoice ? "dialog" : "status"}
          aria-label="WorldState startup"
          // Once a mode exists the gate is purely decorative while it
          // lifts; it must never trap input if its exit is delayed.
          style={{ pointerEvents: mode === null ? "auto" : "none" }}
          exit={
            reduced
              ? { opacity: 0 }
              : { opacity: 0, scale: 1.035, filter: "blur(6px)" }
          }
          transition={{ duration: 0.8, ease: gravitationalEase }}
        >
          <motion.span
            className="connect-gate__bar connect-gate__bar--top"
            aria-hidden="true"
            initial={reduced ? false : { scaleY: 1 }}
            animate={{ scaleY: resolved ? 0.6 : 1 }}
            transition={{ duration: 1.1, ease: gravitationalEase }}
          />
          <div className="connect-gate__console">
            <motion.div
              className="connect-gate__mark"
              initial={reduced ? false : { opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.9, ease: gravitationalEase }}
              aria-hidden="true"
            >
              <span className="connect-gate__mark-ring" />
              <span className="connect-gate__mark-core">WS</span>
            </motion.div>
            <div className="connect-gate__log" aria-live="polite">
              {lines.map((line, index) => (
                <TypedLine
                  key={line.text}
                  line={line}
                  delay={reduced ? 0 : 0.3 + index * 0.42}
                  reduced={reduced}
                />
              ))}
            </div>

            {needsChoice && (
              <motion.div
                className="connect-gate__actions"
                initial={reduced ? false : { opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  duration: 0.7,
                  ease: gravitationalEase,
                  delay: reduced ? 0 : lines.length * 0.42 + 0.4,
                }}
              >
                {backendStatus === "ready" && !authenticated && (
                  <p className="connect-gate__hint">
                    Run <code>scripts\run.ps1</code> — the launcher opens the
                    interface with a one-time link token in the URL fragment.
                  </p>
                )}
                <button
                  type="button"
                  className="control-button"
                  onClick={() => {
                    enterSimulation();
                  }}
                >
                  enter simulation
                </button>
                <p className="connect-gate__hint connect-gate__hint--sub">
                  Deterministic desk-change replay, computed entirely in this
                  browser. Clearly labeled; no backend, no camera.
                </p>
              </motion.div>
            )}
          </div>
          <motion.span
            className="connect-gate__bar connect-gate__bar--bottom"
            aria-hidden="true"
            initial={reduced ? false : { scaleY: 1 }}
            animate={{ scaleY: resolved ? 0.6 : 1 }}
            transition={{ duration: 1.1, ease: gravitationalEase }}
          />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
