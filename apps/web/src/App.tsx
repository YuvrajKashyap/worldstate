import { lazy, Suspense } from "react";

import { FoundationPanel } from "./components/FoundationPanel";
import { SystemBadge } from "./components/SystemBadge";
import { TimelineStrip } from "./components/TimelineStrip";

const WorldViewport = lazy(() => import("./components/WorldViewport"));

export function App() {
  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="wordmark" href="/" aria-label="WorldState home">
          <span className="wordmark__mark" aria-hidden="true">
            W
          </span>
          <span>WorldState</span>
        </a>
        <p className="topbar__descriptor">
          Persistent visual memory / foundation
        </p>
        <SystemBadge />
      </header>

      <section className="workspace" aria-label="WorldState foundation">
        <Suspense
          fallback={
            <div className="viewport viewport--loading" role="status">
              Preparing spatial renderer
            </div>
          }
        >
          <WorldViewport />
        </Suspense>
        <FoundationPanel />
      </section>

      <TimelineStrip />
    </main>
  );
}
