/** Tiny mono sparkline that draws itself on mount. */

import { motion, useReducedMotion } from "motion/react";
import { useId, useMemo } from "react";

type SparklineProps = {
  values: number[];
  width?: number;
  height?: number;
  stroke?: string;
  label: string;
};

export function Sparkline({
  values,
  width = 96,
  height = 22,
  stroke = "var(--lumen)",
  label,
}: SparklineProps) {
  const reduced = useReducedMotion() ?? false;
  const gradientId = useId();

  const path = useMemo(() => {
    if (values.length < 2) {
      return "";
    }
    const max = Math.max(...values, 1e-6);
    const min = Math.min(...values);
    const range = Math.max(1e-6, max - min);
    return values
      .map((value, index) => {
        const x = (index / (values.length - 1)) * width;
        const y = height - 2 - ((value - min) / range) * (height - 5);
        return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }, [values, width, height]);

  if (path === "") {
    return <span className="sparkline sparkline--empty" aria-hidden="true" />;
  }
  const lastValue = values[values.length - 1] ?? 0;
  const max = Math.max(...values, 1e-6);
  const min = Math.min(...values);
  const range = Math.max(1e-6, max - min);
  const dotY = height - 2 - ((lastValue - min) / range) * (height - 5);

  return (
    <svg
      className="sparkline"
      width={width}
      height={height}
      viewBox={`0 0 ${String(width)} ${String(height)}`}
      role="img"
      aria-label={label}
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor={stroke} stopOpacity="0.15" />
          <stop offset="100%" stopColor={stroke} stopOpacity="0.9" />
        </linearGradient>
      </defs>
      <motion.path
        d={path}
        fill="none"
        stroke={`url(#${gradientId})`}
        strokeWidth="1.4"
        initial={reduced ? false : { pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.9, ease: [0.22, 0.8, 0.28, 1] }}
      />
      <circle cx={width} cy={dotY} r="1.8" fill={stroke} />
    </svg>
  );
}
