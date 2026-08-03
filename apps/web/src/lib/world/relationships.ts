/**
 * Client-derived spatial relationships for the animated scene graph.
 *
 * The backend exposes authoritative relationships over REST; this module
 * derives the same vocabulary from viewer geometry so the graph stays
 * animated between fetches — including while scrubbing history. Derived
 * edges are labeled as derived and use explicit tolerances (EVT-003).
 */

import type { Presence } from "../protocol/messages";

export type GraphNode = {
  id: string;
  position: [number, number, number] | null;
  confidence: number;
  presence: Presence;
};

export type GraphEdge = {
  key: string;
  from: string;
  to: string;
  kind: "left_of" | "right_of" | "above" | "below" | "near";
  confidence: number;
  derived: boolean;
};

const NEAR_TOLERANCE_M = 0.55;
const AXIS_TOLERANCE_M = 0.12;

export function deriveEdges(nodes: GraphNode[]): GraphEdge[] {
  const edges: GraphEdge[] = [];
  const present = nodes.filter(
    (node) =>
      node.position !== null &&
      node.presence !== "missing" &&
      node.presence !== "archived",
  );

  for (let i = 0; i < present.length; i += 1) {
    for (let j = i + 1; j < present.length; j += 1) {
      const a = present[i];
      const b = present[j];
      if (a === undefined || b === undefined) {
        continue;
      }
      const pa = a.position;
      const pb = b.position;
      if (pa === null || pb === null) {
        continue;
      }
      const dx = pb[0] - pa[0];
      const dy = pb[1] - pa[1];
      const dz = pb[2] - pa[2];
      const dist = Math.hypot(dx, dy, dz);
      const confidence = Math.min(a.confidence, b.confidence);

      if (dist <= NEAR_TOLERANCE_M) {
        edges.push({
          key: `${a.id}:${b.id}:near`,
          from: a.id,
          to: b.id,
          kind: "near",
          confidence,
          derived: true,
        });
      }
      if (Math.abs(dx) > AXIS_TOLERANCE_M && Math.abs(dx) >= Math.abs(dy)) {
        edges.push({
          key: `${a.id}:${b.id}:x`,
          from: a.id,
          to: b.id,
          kind: dx > 0 ? "left_of" : "right_of",
          confidence,
          derived: true,
        });
      } else if (Math.abs(dy) > AXIS_TOLERANCE_M) {
        edges.push({
          key: `${a.id}:${b.id}:y`,
          from: a.id,
          to: b.id,
          kind: dy > 0 ? "below" : "above",
          confidence,
          derived: true,
        });
      }
    }
  }
  return edges;
}
