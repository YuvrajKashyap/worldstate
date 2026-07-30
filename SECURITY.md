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
- Continuous webcam video is not persisted by default.
- Model paths and absolute local paths are not returned by APIs.
- Private captures, model weights, and generated artifacts are ignored by Git.
- Public or LAN exposure requires a new threat review.

See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) for the current model.
