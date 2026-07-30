# ADR 0003: Measure model providers before product commitment

Status: Accepted

## Context

Research repositories have changing dependencies and may exceed the target
8 GB GPU budget.

## Decision

Keep geometry, perception, and appearance models behind provider interfaces.
Run explicit feasibility gates before naming a provider as the supported
product path.

## Consequences

- Product behavior is not coupled to one checkpoint.
- Setup remains lightweight.
- Provider selection is slower initially but evidence-based.
