# ADR 0002: Point and voxel state is the geometric source of truth

Status: Accepted

## Context

Gaussian splatting is visually compelling but awkward for object identity,
change detection, measurements, and evaluation.

## Decision

Use point, surfel, or voxel geometry as the internal source of truth. Render a
splat-like holographic representation as a view of that state.

## Consequences

- Geometry remains measurable and testable.
- Visual rendering can evolve independently.
- A future Gaussian representation is an optional artifact, not the database.
