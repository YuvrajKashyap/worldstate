# Threat model

Status: Foundation review
Scope: Local single-user application bound to loopback

## Protected assets

- Camera frames and videos.
- Spatial layout and object history.
- Selected evidence images.
- Embeddings and geometry.
- Local filesystem paths.
- Model access tokens.
- Experiment and dataset provenance.

## Trust boundaries

1. Browser to local API.
2. API to model providers.
3. Application to local artifact store.
4. Developer tooling to external model and package registries.
5. Future phone capture to the local machine; not yet enabled.

## Principal threats

### Untrusted browser origin

Risk: another local or remote page connects to the camera-processing API.

Controls:

- Exact origin allowlist.
- Loopback binding.
- Reject WebSockets before acceptance.
- No wildcard CORS.

### Persistence surprise

Risk: a user believes frames are ephemeral while artifacts are retained.

Controls:

- Persistence disabled by default.
- Visible recording and retention state.
- Store only selected evidence.
- Per-scene retention summary and complete deletion.

### Path or secret disclosure

Risk: diagnostics expose usernames, local paths, or model tokens.

Controls:

- Public artifact IDs.
- Structured response schemas.
- Redacted logs.
- Environment variables and ignored secret files.

### Resource exhaustion

Risk: large uploads, unbounded queues, or concurrent models exhaust RAM, VRAM,
or disk.

Controls:

- Size and duration limits.
- One frame in flight.
- Bounded job queue.
- Sequential heavy providers.
- Cancellation, timeouts, and artifact quotas.

### Supply-chain risk

Risk: model code or package updates execute unreviewed behavior.

Controls:

- Lock dependencies.
- Pin model revisions and checkpoint hashes.
- Record licenses.
- Review install scripts.
- Keep model downloads outside bootstrap and CI.

### Accidental sensitive inference

Risk: editable prompts or future providers are used to infer protected traits.

Controls:

- Server-side rejected prompt categories.
- No persistent person identities.
- Provider capability review.
- Tests for policy boundaries.

## Out of scope for the foundation

- Public network exposure.
- Multiple mutually untrusted users.
- Cloud synchronization.
- Remote model APIs.
- Security or access-control decisions.

These require a new review before implementation.
