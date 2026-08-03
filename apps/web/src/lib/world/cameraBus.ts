/**
 * Camera intent bus.
 *
 * Pointer drag, keyboard, and HoloConsole gestures all steer the same
 * spherical target; the in-canvas rig eases toward it every frame. Keeping
 * intents outside React avoids re-render churn at gesture rates.
 */

export type CameraIntent = {
  theta: number;
  phi: number;
  radius: number;
  target: [number, number, number];
  /** Monotonic counter so the rig can detect focus jumps. */
  focusVersion: number;
};

const DEFAULT_INTENT: CameraIntent = {
  theta: Math.PI * 0.18,
  phi: Math.PI * 0.34,
  radius: 3.4,
  target: [0, 0.34, 0],
  focusVersion: 0,
};

const MIN_PHI = 0.12;
const MAX_PHI = Math.PI * 0.49;
const MIN_RADIUS = 1.2;
const MAX_RADIUS = 7.5;

const intent: CameraIntent = { ...DEFAULT_INTENT, target: [0, 0.34, 0] };

export const cameraBus = {
  read(): Readonly<CameraIntent> {
    return intent;
  },
  orbit(dTheta: number, dPhi: number): void {
    intent.theta += dTheta;
    intent.phi = Math.min(MAX_PHI, Math.max(MIN_PHI, intent.phi + dPhi));
  },
  zoom(factor: number): void {
    intent.radius = Math.min(
      MAX_RADIUS,
      Math.max(MIN_RADIUS, intent.radius * factor),
    );
  },
  pan(dx: number, dz: number): void {
    intent.target = [
      Math.min(2.2, Math.max(-2.2, intent.target[0] + dx)),
      intent.target[1],
      Math.min(2.2, Math.max(-2.2, intent.target[2] + dz)),
    ];
  },
  focus(target: [number, number, number], radius?: number): void {
    intent.target = target;
    if (radius !== undefined) {
      intent.radius = Math.min(MAX_RADIUS, Math.max(MIN_RADIUS, radius));
    }
    intent.focusVersion += 1;
  },
  reset(): void {
    intent.theta = DEFAULT_INTENT.theta;
    intent.phi = DEFAULT_INTENT.phi;
    intent.radius = DEFAULT_INTENT.radius;
    intent.target = [...DEFAULT_INTENT.target];
    intent.focusVersion += 1;
  },
};
