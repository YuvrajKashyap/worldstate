# API and live protocol v1

The source of truth is generated on every release:

- `packages/contracts/openapi.json`
- `packages/contracts/protocol-v1.schema.json`
- `packages/contracts/generated/openapi.d.ts`
- `packages/contracts/fixtures/desk-change-v1.json`

Claude may consume `@worldstate/contracts` without importing backend or
framework code. During development Vite uses `http://127.0.0.1:8000`; production
is served same-origin by FastAPI from `apps/web/dist`.

## Browser bootstrap

1. Read `bootstrap` from `location.hash`.
2. `POST /api/v1/bootstrap` with `{ "token": value }` and the exact browser
   origin.
3. Keep the returned CSRF token in memory only.
4. Immediately remove the fragment with `history.replaceState`.
5. Send credentials with REST and WebSocket requests.
6. Include `X-WorldState-CSRF` on state-changing REST requests.

The session credential is available only as an HttpOnly SameSite cookie.

## Live handshake

Connect to `/api/v1/live`, then send `client.hello` before any other message.
The server responds with `server.ready`. Submit exactly one binary frame and
wait for `frame.result` before capturing the next. There is no client-side
queue.

The 28-byte big-endian binary header is:

| Offset | Type | Meaning |
| --- | --- | --- |
| 0 | 4 bytes | ASCII `WSF1` |
| 4 | uint64 | monotonically increasing sequence |
| 12 | float64 | capture Unix timestamp in seconds |
| 20 | uint16 | encoded width |
| 22 | uint16 | encoded height |
| 24 | uint8 | `1` JPEG, `2` WebP, `3` RGBA, `4` I420 |
| 25 | 3 bytes | reserved zeros |
| 28 | bytes | bounded frame payload for the selected encoding |

Control and result messages are strict discriminated JSON unions. Unknown
fields fail validation. HoloConsole mutations use `command.submit` with an
idempotency key and optional expected entity-state version. Gesture recognition
and raycasting stay in Claude's client.

The first-party webcam client requests only `frame.result` and
`command.submit`. This keeps a processed frame from also arriving as redundant
`world.patch` and `event.batch` messages. For v1 compatibility, clients that
omit the capabilities field receive the original `world.patch`, `event.batch`,
and `frame.result` stream.

## Compatibility policy

Additive optional fields may remain protocol v1. Removing, renaming, changing
meaning, changing requiredness, or changing the binary envelope requires a new
protocol version and parallel support during migration. CI regenerates the
artifacts and fails if the working tree changes.
