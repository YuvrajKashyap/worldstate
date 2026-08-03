# Claude frontend handoff

Claude owns every visual and interaction decision under `apps/web/**`.
WorldState backend code does not prescribe component structure, visual style,
state library usage, or the implementation of webcam gestures.

Backend guarantees:

- versioned OpenAPI and WebSocket JSON Schema;
- generated framework-neutral TypeScript types;
- binary frame encoder helper;
- deterministic replay provider and Desk Change fixture;
- exact same-origin production serving;
- explicit capabilities and resource limits from `/api/v1/system`;
- stable opaque IDs, UTC timestamps, meters, scene-local coordinates, evidence,
  uncertainty, and append-only history;
- idempotent command acknowledgements.

Claude must:

- implement the one-time fragment bootstrap from `API_PROTOCOL.md`;
- keep the CSRF token only in memory;
- allow one live frame in flight and stop every media track on teardown;
- send real capture timestamps and monotonic sequences;
- treat `unavailable` and `degraded` capabilities as normal states;
- never present raw confidence as calibrated probability;
- provide keyboard/mouse parity and reduced-motion behavior for gesture actions;
- pass generated-contract consumption and replay end-to-end tests.

The fixture is sufficient to develop Ghost Mode, Time Scrubber, Change Pulses,
Object Memory, Uncertainty View, Scene Graph, Last-Seen Search, Active Scan
Coach, and X-ray Memory without CUDA or model weights.
