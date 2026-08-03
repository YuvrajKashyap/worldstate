/**
 * Assembles what the viewer should render for the current moment:
 * live world state, or a pure historical lookup while scrubbing
 * (never mutating live memory — HOL-005).
 */

import { useMemo } from "react";

import { deriveEdges, type GraphEdge } from "../../lib/world/relationships";
import type { Presence } from "../../lib/protocol/messages";
import {
  estimateMotion,
  type Position,
} from "../../lib/world/prediction";
import {
  entityStateAt,
  ghostMarkers,
  useWorldStore,
  type GhostMarker,
  type Pulse,
} from "../../state/worldStore";
import { useUiStore } from "../../state/uiStore";

export type EntityView = {
  id: string;
  label: string;
  presence: Presence;
  confidence: number;
  uncertainty: number;
  position: [number, number, number] | null;
  bounds: [number, number, number] | null;
  positionVelocity: Position | null;
  observedAt: number | null;
  stale: boolean;
  selected: boolean;
  pinned: boolean;
  hidden: boolean;
  eventCount: number;
};

export type ViewData = {
  entities: EntityView[];
  ghosts: GhostMarker[];
  pulses: Pulse[];
  edges: GraphEdge[];
  scrubbing: boolean;
  viewTime: number | null;
};

const STALE_AFTER_MS = 6_000;

export function useViewData(): ViewData {
  const entities = useWorldStore((state) => state.entities);
  const order = useWorldStore((state) => state.order);
  const events = useWorldStore((state) => state.events);
  const pulses = useWorldStore((state) => state.pulses);
  const lastFrameAt = useWorldStore((state) => state.lastFrameAt);
  const timelineMode = useUiStore((state) => state.timelineMode);
  const scrubTime = useUiStore((state) => state.scrubTime);
  const selectedEntityId = useUiStore((state) => state.selectedEntityId);
  const pinnedEntityIds = useUiStore((state) => state.pinnedEntityIds);
  const hiddenEntityIds = useUiStore((state) => state.hiddenEntityIds);
  const layers = useUiStore((state) => state.layers);

  return useMemo(() => {
    const scrubbing = timelineMode === "scrub" && scrubTime !== null;
    const viewTime = scrubbing ? scrubTime : lastFrameAt;

    const views: EntityView[] = [];
    for (const id of order) {
      const record = entities[id];
      if (record === undefined) {
        continue;
      }
      const hidden = hiddenEntityIds.includes(id);
      if (scrubbing) {
        const snapshot = entityStateAt(record, scrubTime);
        if (snapshot === null) {
          continue;
        }
        views.push({
          id,
          label: record.label,
          presence: snapshot.presence,
          confidence: snapshot.confidence,
          uncertainty: snapshot.uncertainty,
          position: snapshot.position,
          bounds: snapshot.bounds,
          positionVelocity: null,
          observedAt: snapshot.at,
          stale: false,
          selected: selectedEntityId === id,
          pinned: pinnedEntityIds.includes(id),
          hidden,
          eventCount: record.eventCount,
        });
      } else {
        const motion = estimateMotion(record.history);
        views.push({
          id,
          label: record.label,
          presence: record.presence,
          confidence: record.confidence,
          uncertainty: record.uncertainty,
          position: record.position,
          bounds: record.bounds,
          positionVelocity: motion?.positionVelocity ?? null,
          observedAt: motion?.observedAt ?? record.lastSeenAt,
          stale:
            record.lastVisibleAt !== null &&
            lastFrameAt !== null &&
            lastFrameAt - record.lastVisibleAt > STALE_AFTER_MS,
          selected: selectedEntityId === id,
          pinned: pinnedEntityIds.includes(id),
          hidden,
          eventCount: record.eventCount,
        });
      }
    }

    const allGhosts = layers.ghosts ? ghostMarkers(entities, events) : [];
    const ghosts = scrubbing
      ? allGhosts.filter((ghost) => ghost.at <= scrubTime)
      : allGhosts;

    const visiblePulses: Pulse[] = scrubbing
      ? pulses.filter(
          (pulse) => pulse.at <= scrubTime && scrubTime - pulse.at < 2_500,
        )
      : pulses;

    const edges = layers.graph
      ? deriveEdges(
          views
            .filter((view) => !view.hidden)
            .map((view) => ({
              id: view.id,
              position: view.position,
              confidence: view.confidence,
              presence: view.presence,
            })),
        )
      : [];

    return {
      entities: views,
      ghosts,
      pulses: visiblePulses,
      edges,
      scrubbing,
      viewTime,
    };
  }, [
    entities,
    order,
    events,
    pulses,
    lastFrameAt,
    timelineMode,
    scrubTime,
    selectedEntityId,
    pinnedEntityIds,
    hiddenEntityIds,
    layers,
  ]);
}
