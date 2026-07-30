# Contributing

WorldState is organized around explicit domain boundaries and reproducible
evidence. Changes should keep those boundaries intact.

## Before opening a change

1. Read [product_spec.md](product_spec.md).
2. Read [Architecture](docs/ARCHITECTURE.md).
3. Record a new ADR when changing a durable architectural decision.
4. Keep model integrations behind provider interfaces.
5. Do not add large model weights, private captures, or generated datasets to
   Git.

## Development

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

## Change quality

- Keep modules small and named for one responsibility.
- Add tests for behavior and failure paths.
- Preserve typed API and domain boundaries.
- Include measured evidence for performance or accuracy claims.
- Document privacy and licensing changes.
- Stage only files related to the intended change.

## Commit and pull request expectations

- Use a short, specific commit subject.
- Explain what changed, why, user impact, and validation in the PR.
- Do not mark a research result as current unless its raw artifact and
  configuration are reproducible.
