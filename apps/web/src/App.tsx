import { useReducedMotion } from "motion/react";
import { lazy, Suspense } from "react";

import { Announcer } from "./components/a11y/Announcer";
import { EntityDock } from "./components/a11y/EntityDock";
import { KeyboardLayer } from "./components/chrome/KeyboardLayer";
import { SystemRail } from "./components/chrome/SystemRail";
import { TopBar } from "./components/chrome/TopBar";
import { ConnectGate } from "./components/connect/ConnectGate";
import { HoloOverlay } from "./components/holo/HoloOverlay";
import { EventFeed } from "./components/hud/EventFeed";
import { EvidenceDrawer } from "./components/hud/EvidenceDrawer";
import { ObjectMemoryPanel } from "./components/hud/ObjectMemoryPanel";
import { ScanCoach } from "./components/hud/ScanCoach";
import { ScanPanel } from "./components/hud/ScanPanel";
import { SearchPalette } from "./components/hud/SearchPalette";
import { TimeDeck } from "./components/hud/TimeDeck";
import { VideoDock } from "./components/hud/VideoDock";
import { useUiStore } from "./state/uiStore";

const WorldCanvas = lazy(() => import("./components/world/WorldCanvas"));

function ActionCluster() {
  const setSearchOpen = useUiStore((state) => state.setSearchOpen);
  const setScanPanelOpen = useUiStore((state) => state.setScanPanelOpen);
  const scanPanelOpen = useUiStore((state) => state.scanPanelOpen);
  const setHelpOpen = useUiStore((state) => state.setHelpOpen);
  return (
    <div className="action-cluster" role="toolbar" aria-label="Tools">
      <button
        type="button"
        className="icon-button"
        title="Last-seen search (Ctrl+K)"
        onClick={() => {
          setSearchOpen(true);
        }}
      >
        ⌕
      </button>
      <button
        type="button"
        className="icon-button"
        title="Spatial scan"
        aria-pressed={scanPanelOpen}
        onClick={() => {
          setScanPanelOpen(!scanPanelOpen);
        }}
      >
        ⇪
      </button>
      <button
        type="button"
        className="icon-button"
        title="Keyboard controls (?)"
        onClick={() => {
          setHelpOpen(true);
        }}
      >
        ?
      </button>
    </div>
  );
}

export function App() {
  const reducedMotion = useReducedMotion() ?? false;
  const scrubbing = useUiStore((state) => state.timelineMode === "scrub");

  return (
    <div className="app-shell">
      <ConnectGate />
      <TopBar />
      <div className="workspace">
        <SystemRail />
        <main
          className={`viewport${scrubbing ? " viewport--memory" : ""}`}
          aria-label="Spatial memory viewport"
        >
          <Suspense
            fallback={
              <div className="viewport__loading" role="status">
                <span className="viewport__loading-ring" aria-hidden="true" />
                preparing spatial renderer
              </div>
            }
          >
            <WorldCanvas reducedMotion={reducedMotion} />
          </Suspense>
          <span className="viewport__frame" aria-hidden="true" />
          <EventFeed />
          <ScanCoach />
          <ActionCluster />
          <VideoDock />
          <EntityDock />
          <ObjectMemoryPanel />
          <ScanPanel />
          <HoloOverlay />
        </main>
      </div>
      <TimeDeck />
      <SearchPalette />
      <EvidenceDrawer />
      <KeyboardLayer />
      <Announcer />
    </div>
  );
}
