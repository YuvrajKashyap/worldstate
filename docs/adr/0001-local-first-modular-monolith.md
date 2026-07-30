# ADR 0001: Local-first modular monolith

Status: Accepted

## Context

WorldState serves one local operator and one GPU. The difficult work is
perception, persistent state, and interaction, not distributed infrastructure.

## Decision

Use one browser client, one FastAPI coordinator, one bounded GPU scheduler, and
a framework-independent core package. Bind to loopback by default.

## Consequences

- Fewer operational failure modes.
- Clear privacy boundary.
- Easy local profiling.
- Provider processes may be separated later when dependency isolation requires
  it.
