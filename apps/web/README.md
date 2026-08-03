# WorldState interface

The visual and interaction layer of WorldState: a spatial-memory console
that renders a persistent, queryable 3D history of a physical workspace.

## Running it

- **With the backend** (full experience): `scripts\run.ps1` builds this app
  and launches the secured same-origin server; the launcher opens the
  browser with a one-time `#bootstrap=` token. For frontend development,
  run the backend on `127.0.0.1:8000` and `pnpm dev:web` on `5173` — the
  gate performs the fragment bootstrap automatically.
- **Without any backend**: the connect gate offers a deterministic
  in-browser simulation of the Desk Change replay (labeled SIMULATION
  everywhere). No camera, no Python, no GPU.

## What's inside

- `src/lib/protocol` — protocol v1 message types and builders (mirrors
  `packages/contracts/protocol-v1.schema.json` exactly).
- `src/lib/live` — the live pipeline: webcam lifecycle, JPEG → `WSF1`
  binary envelopes, a capture loop that keeps exactly one frame in flight
  and counts skipped intervals, the WebSocket transport, and the
  deterministic mock world used for the simulation and tests.
- `src/state` — session controller, temporal world memory (append-only
  per-entity history rings that power the Time Scrubber and Ghost Mode),
  interface state.
- `src/components/world` — the R3F memory volume: shader grid floor that
  ripples on change events, swirl-in particle field, entity holograms with
  the X-ray presence grammar, ghost layer, change pulses, scene-graph
  overlay, camera rig with drag inertia; a fully functional top-down SVG
  map replaces it when WebGL is unavailable.
- `src/components/hud` — perception dock, time deck, Object Memory
  dossier, evidence drawer, last-seen search palette, scan coach, scan
  jobs panel.
- `src/lib/holo` + `src/components/holo` — HoloConsole: MediaPipe hand
  landmarks (client-side), one-euro smoothing, hysteresis-based gesture
  recognition, and an XState interaction machine with deliberate two-palm
  summon, confidence display, and instant cancel.

## Gesture model availability

The MediaPipe wasm runtime ships from this origin. In production, the backend
serves the checksum-verified hand landmark model from
`/models/hand_landmarker.task` after it is acquired through
`scripts\models.ps1 -Defaults -IncludeReconstruction`. Development mode may
fall back to the MediaPipe CDN. When neither source is available, HoloConsole
reports itself unavailable and the interface keeps full keyboard/mouse parity
— every gesture has a key (press `?`).

## Accessibility

Keyboard operability throughout, an accessible parallel entity list
mirroring the canvas, polite live-region announcements for world changes,
no color-only state signals, and reduced-motion variants for every
animated surface.
