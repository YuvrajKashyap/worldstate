/** House motion vocabulary. Every tween in the app uses these values. */

export const gravitationalEase = [0.16, 1, 0.3, 1] as const;
export const orbitalEase = [0.22, 0.8, 0.28, 1] as const;
export const signalEase = [0.4, 0, 0.2, 1] as const;

export const settleSpring = {
  type: "spring",
  stiffness: 260,
  damping: 22,
  mass: 0.5,
} as const;

export const popSpring = {
  type: "spring",
  stiffness: 380,
  damping: 21,
  mass: 0.6,
} as const;

export const drawerSpring = {
  type: "spring",
  stiffness: 210,
  damping: 26,
  mass: 0.8,
} as const;

export const slowReveal = { duration: 0.85, ease: gravitationalEase } as const;
export const microSwap = { duration: 0.18, ease: signalEase } as const;

/** Deal-in used by panel stacks; per-sibling stagger is applied by callers. */
export const dealIn = {
  hidden: { opacity: 0, y: 26, rotateX: -14, scale: 0.985 },
  visible: {
    opacity: 1,
    y: 0,
    rotateX: 0,
    scale: 1,
    transition: { duration: 0.72, ease: gravitationalEase },
  },
} as const;

/** Dossier unseal for contextual panels (clip wipe, no blur on lists). */
export const unseal = {
  hidden: { clipPath: "inset(0 100% 0 0)", x: -14, opacity: 0.4 },
  visible: {
    clipPath: "inset(0 0% 0 0)",
    x: 0,
    opacity: 1,
    transition: { duration: 0.9, ease: gravitationalEase },
  },
} as const;
