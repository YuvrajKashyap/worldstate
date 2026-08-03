/** WorldState visual constants shared by CSS, canvas, and WebGL surfaces. */

export const palette = {
  blackGlass: "#08100f",
  deepScan: "#0d1a18",
  mineral: "#1d2b28",
  lumen: "#b5f2e7",
  archive: "#f0a86b",
  memory: "#a8a0e8",
  bone: "#eaf0ec",
  muted: "#8ba09a",
  alarm: "#f27a6b",
} as const;

/** Presence lifecycle → X-ray Memory visual grammar. */
export const presenceColor = {
  visible: palette.lumen,
  occluded: palette.bone,
  predicted: palette.archive,
  missing: palette.alarm,
  rediscovered: palette.lumen,
  archived: palette.muted,
} as const;

export const presenceLabel = {
  visible: "observed",
  occluded: "occluded",
  predicted: "predicted",
  missing: "missing",
  rediscovered: "rediscovered",
  archived: "archived",
} as const;

/** Event kind → change-pulse color. */
export const eventColor = {
  added: palette.lumen,
  moved: palette.memory,
  rotated: palette.memory,
  removed: palette.alarm,
  occluded: palette.bone,
  rediscovered: palette.archive,
  confidence_changed: palette.muted,
} as const;

export const eventGlyph = {
  added: "+",
  moved: "→",
  rotated: "↻",
  removed: "−",
  occluded: "◍",
  rediscovered: "✦",
  confidence_changed: "≈",
} as const;
