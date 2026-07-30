# Privacy

WorldState processes views of physical spaces. Privacy is a product requirement,
not a deployment afterthought.

## Defaults

- Local inference.
- API bound to `127.0.0.1`.
- Exact browser-origin allowlist.
- Persistence disabled in the foundation configuration.
- No continuous webcam recording.
- No telemetry or cloud model calls.
- No persistent person identity.
- No sensitive-trait inference.

## Data classes

### Ephemeral

- Live webcam frames.
- Transient hand and person masks.
- Intermediate tensors.
- Uncommitted object hypotheses.

These stay in memory and are released after the bounded processing window.

### Persistent when enabled

- Scene and object metadata.
- Historical states and events.
- Selected evidence keyframes.
- Masks, geometry, and embeddings needed for the saved scene.
- Model and experiment provenance.

### Never committed

- Private captures.
- User scene stores.
- Model weights.
- Credentials.
- Absolute local paths in generated reports.

## People

People and hands may be detected to prevent static-map corruption and to support
HoloConsole. They remain transient agents. WorldState does not perform face
recognition, persistent re-identification, demographic classification, or
sensitive-trait inference.

## User controls

The product must provide:

- Clear capture state.
- Explicit persistence state.
- Per-scene retention summary.
- Export before deletion.
- Complete scene deletion.
- Capture stop that closes every browser media track.

## Expansion boundary

LAN access, phone live streaming, cloud sync, shared scenes, or public hosting
requires a new threat model and explicit product decision.
