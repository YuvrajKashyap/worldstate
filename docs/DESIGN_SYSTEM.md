# Design system

## Subject and job

WorldState is a spatial-memory instrument for one operator. The primary screen's
job is to make the state of a real place understandable and manipulable.

## Visual thesis

The interface is organized around a confidence-aware **memory volume**, not a
dashboard grid. The world viewport dominates. Telemetry and controls behave like
precise instruments around it.

## Palette

| Token | Value | Use |
|---|---|---|
| Black glass | `#08100f` | Canvas and page base |
| Deep scan | `#0d1a18` | Raised surfaces |
| Mineral | `#1d2b28` | Borders and inactive geometry |
| Lumen | `#b5f2e7` | Observed state and primary action |
| Archive amber | `#f0a86b` | Predicted and changed state |
| Memory violet | `#a8a0e8` | Historical state |
| Bone | `#eaf0ec` | Primary text |

## Typography

- Familjen Grotesk: product and display text.
- JetBrains Mono: timestamps, metrics, coordinates, evidence, and status.

## Layout

```text
+---------------------------------------------------------------+
| WorldState / scene                               system status |
+----------------------------------------------+----------------+
|                                              |                |
|                                              | object /       |
|              memory volume                   | system rail    |
|                                              |                |
|                                              |                |
+----------------------------------------------+----------------+
| live ------------------------------------------------ history  |
+---------------------------------------------------------------+
```

The right rail may collapse. Object Memory appears only after selection. The
timeline is a temporal instrument, not a decorative footer.

## State grammar

- Solid lumen: directly observed.
- Wireframe lumen: occluded.
- Amber pulse: predicted or newly changed.
- Violet ghost: historical state.
- Red edge: missing from an expected location.
- Unstable mineral particles: uncertain geometry.

## Motion

- Use one orchestrated scan-to-memory transition.
- Interpolate state changes through time.
- Avoid ambient motion that competes with actual uncertainty.
- Reduced-motion mode removes drift, particles, and nonessential interpolation.

## Copy

Use direct user language:

- "Start camera"
- "Scan workspace"
- "Keep evidence"
- "Return to live"
- "No scene active"

Do not label product controls with implementation terms such as "initialize
WebSocket" or "run inference."

## Accessibility

- Visible focus.
- Keyboard and pointer parity for every gesture.
- Accessible object list parallel to the canvas.
- Text or shape distinction alongside color.
- Minimum 44 px interactive targets on touch layouts.
