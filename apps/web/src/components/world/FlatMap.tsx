/**
 * No-WebGL fallback: a top-down instrument map with the same presence
 * grammar, selection, ghosts, and pulses. Fully keyboard operable — each
 * entity is a real button.
 */

import { eventColor, presenceColor, presenceLabel } from "../../lib/palette";
import { toMap } from "../../lib/world/space";
import { useUiStore } from "../../state/uiStore";
import type { ViewData } from "./useViewData";

const WIDTH = 900;
const HEIGHT = 560;

export function FlatMap({ view }: { view: ViewData }) {
  const select = useUiStore((state) => state.select);
  const selectedEntityId = useUiStore((state) => state.selectedEntityId);

  return (
    <div className="flat-map" data-testid="flat-map">
      <p className="flat-map__notice" role="status">
        3D rendering is unavailable here — showing the top-down instrument
        map. All memory features remain active.
      </p>
      <svg
        viewBox={`0 0 ${String(WIDTH)} ${String(HEIGHT)}`}
        className="flat-map__svg"
        role="img"
        aria-label="Top-down map of remembered objects"
      >
        <defs>
          <radialGradient id="flatmap-glow" cx="50%" cy="50%" r="60%">
            <stop offset="0%" stopColor="rgba(181,242,231,0.09)" />
            <stop offset="100%" stopColor="rgba(181,242,231,0)" />
          </radialGradient>
        </defs>
        <rect width={WIDTH} height={HEIGHT} fill="#08100f" />
        <rect width={WIDTH} height={HEIGHT} fill="url(#flatmap-glow)" />
        {Array.from({ length: 11 }, (_, i) => (
          <line
            key={`v${String(i)}`}
            x1={(WIDTH / 10) * i}
            y1={0}
            x2={(WIDTH / 10) * i}
            y2={HEIGHT}
            stroke="rgba(181,242,231,0.07)"
          />
        ))}
        {Array.from({ length: 8 }, (_, i) => (
          <line
            key={`h${String(i)}`}
            x1={0}
            y1={(HEIGHT / 7) * i}
            x2={WIDTH}
            y2={(HEIGHT / 7) * i}
            stroke="rgba(181,242,231,0.07)"
          />
        ))}
        {view.ghosts.map((ghost) => {
          const point = toMap(ghost.position, WIDTH, HEIGHT);
          return (
            <circle
              key={ghost.key}
              cx={point.x}
              cy={point.y}
              r={14}
              fill="none"
              stroke={eventColor[ghost.kind]}
              strokeDasharray="3 3"
              opacity={0.5}
            />
          );
        })}
        {view.pulses.map((pulse) => {
          if (pulse.position === null) {
            return null;
          }
          const point = toMap(pulse.position, WIDTH, HEIGHT);
          return (
            <circle
              key={pulse.id}
              cx={point.x}
              cy={point.y}
              r={22}
              fill="none"
              stroke={eventColor[pulse.kind]}
              opacity={0.6}
            />
          );
        })}
        {view.entities
          .flatMap((entity) =>
            entity.hidden || entity.position === null
              ? []
              : [{ ...entity, position: entity.position }],
          )
          .map((entity) => {
            const point = toMap(entity.position, WIDTH, HEIGHT);
            const color = presenceColor[entity.presence];
            const selected = entity.id === selectedEntityId;
            return (
              <g key={entity.id}>
                <circle
                  cx={point.x}
                  cy={point.y}
                  r={selected ? 18 : 13}
                  fill={color}
                  fillOpacity={entity.presence === "missing" ? 0.16 : 0.3}
                  stroke={color}
                  strokeWidth={selected ? 2.5 : 1.4}
                  strokeDasharray={
                    entity.presence === "occluded" ? "4 3" : undefined
                  }
                  role="button"
                  tabIndex={0}
                  aria-label={`${entity.label}, ${presenceLabel[entity.presence]}`}
                  style={{ cursor: "pointer" }}
                  onClick={() => {
                    select(entity.id);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      select(entity.id);
                    }
                  }}
                />
                <text
                  x={point.x}
                  y={point.y - 22}
                  textAnchor="middle"
                  fill={color}
                  className="flat-map__label"
                >
                  {entity.label}
                </text>
              </g>
            );
          })}
      </svg>
    </div>
  );
}
