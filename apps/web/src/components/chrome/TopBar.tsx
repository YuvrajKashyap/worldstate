/** Top chrome: wordmark, mode lamps, live heartbeat, session clock. */

import { AnimatePresence, motion } from "motion/react";

import { microSwap } from "../../lib/motion/presets";
import { useSessionStore } from "../../state/sessionStore";
import { useWorldStore } from "../../state/worldStore";
import { useUiStore } from "../../state/uiStore";

export function TopBar() {
  const mode = useSessionStore((state) => state.mode);
  const providerMode = useSessionStore((state) => state.providerMode);
  const liveStatus = useSessionStore((state) => state.liveStatus);
  const sourceKind = useSessionStore((state) => state.sourceKind);
  const sceneName = useSessionStore((state) => state.sceneName);
  const timelineMode = useUiStore((state) => state.timelineMode);
  const holoActive = useUiStore((state) => state.holoActive);
  const frameCount = useWorldStore((state) => state.telemetry.frameCount);

  const linkLabel =
    liveStatus === "live" && sourceKind === "webcam"
      ? "WEBCAM LIVE"
      : liveStatus === "live" && sourceKind === "synthetic"
        ? "SIMULATION"
        : liveStatus === "starting" && sourceKind === "webcam"
          ? "STARTING CAMERA"
          : mode === "simulation"
            ? "SIMULATION"
            : liveStatus === "idle" &&
                sourceKind === "webcam" &&
                frameCount > 0
              ? "CAMERA OFF · MEMORY"
            : liveStatus === "starting"
              ? "STARTING DEMO"
              : "STANDBY";

  return (
    <header className="topbar" role="banner">
      <div className="wordmark" aria-label="WorldState">
        <span className="wordmark__mark" aria-hidden="true">
          WS
        </span>
        <span className="wordmark__name">
          WorldState
          <span className="wordmark__sub">spatial memory</span>
        </span>
      </div>

      <div className="topbar__center" aria-live="off">
        {sceneName !== null && (
          <span className="topbar__scene">{sceneName}</span>
        )}
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={timelineMode}
            className={`topbar__state topbar__state--${timelineMode}`}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={microSwap}
          >
            {timelineMode === "live" ? "PRESENT" : "MEMORY"}
          </motion.span>
        </AnimatePresence>
        {holoActive && <span className="topbar__holo">HOLO</span>}
      </div>

      <div className="topbar__status">
        {providerMode !== null && (
          <span className="topbar__provider" title="Perception provider mode">
            {providerMode}
          </span>
        )}
        <span
          className={`link-lamp link-lamp--${
            sourceKind === "synthetic" && liveStatus === "live"
              ? "simulation"
              : liveStatus === "live"
                ? "live"
                : liveStatus === "error"
                  ? "error"
                  : "idle"
          }`}
          data-active={liveStatus === "live"}
        >
          <span className="link-lamp__signal" aria-hidden="true" />
          {linkLabel}
        </span>
        <span className="topbar__frames" title="Perception updates received">
          {String(frameCount).padStart(5, "0")}
        </span>
      </div>
    </header>
  );
}
