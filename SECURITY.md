# Security policy

WorldState is an experimental local spatial-computing system. It is not a
security, surveillance, or access-control product.

## Supported versions

Security fixes are applied to the current default branch while the project is
pre-release.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for this repository. Do not include
private camera frames, local paths, access tokens, or sensitive scene data in a
public issue.

## Default security posture

- The API binds to `127.0.0.1`.
- Browser origins are allowlisted exactly.
- A one-time launcher capability becomes an HttpOnly SameSite cookie.
- Mutations require an independent CSRF token.
- Continuous webcam video is not persisted unless the scene policy enables it.
- Model paths and absolute local paths are not returned by APIs.
- Model acquisition is explicit and every loaded file must match the local
  SHA-256 lock.
- Private captures, model weights, and generated artifacts are ignored by Git.
- Public or LAN exposure requires a new threat review.

See [the repository-grounded threat model](docs/worldstate-threat-model.md).
