/**
 * Scene-space mapping.
 *
 * Backend positions are meters in the worldstate_scene_v1 frame:
 * x ∈ [-1, 1] across the desk, y up, z away from the camera (~1.0–1.5).
 * The viewer maps them onto a desk-scale stage centered at the origin.
 */

export type StagePosition = [number, number, number];

export const STAGE_SPREAD_X = 1.35;
export const STAGE_LIFT_Y = 0.32;
export const STAGE_SPREAD_Z = 1.5;
export const STAGE_DEPTH_CENTER = 1.25;

/** Convert relative monocular extents to bounded viewer-stage dimensions. */
export function toStageExtent(
  bounds: [number, number, number],
): StagePosition {
  return [
    Math.max(0.04, Math.min(1.8, bounds[0] * STAGE_SPREAD_X)),
    Math.max(0.03, Math.min(2.2, bounds[1] * 0.9)),
    Math.max(0.035, Math.min(1.2, bounds[2] * STAGE_SPREAD_Z)),
  ];
}

export function toStage(
  position: [number, number, number],
): StagePosition {
  return [
    position[0] * STAGE_SPREAD_X,
    Math.max(0.06, position[1] * 0.9 + STAGE_LIFT_Y),
    (position[2] - STAGE_DEPTH_CENTER) * STAGE_SPREAD_Z,
  ];
}

/** Top-down map projection for the no-WebGL fallback (x right, z down). */
export function toMap(
  position: [number, number, number],
  width: number,
  height: number,
): { x: number; y: number } {
  const stage = toStage(position);
  return {
    x: width / 2 + (stage[0] / 1.6) * (width / 2) * 0.86,
    y: height / 2 + (stage[2] / 1.2) * (height / 2) * 0.8,
  };
}
