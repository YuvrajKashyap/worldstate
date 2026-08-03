import type { Presence } from "../protocol/messages";
import { toStage, toStageExtent } from "./space";

export type SupportEntity = {
  id: string;
  label: string;
  presence: Presence;
  confidence: number;
  uncertainty: number;
  position: [number, number, number] | null;
  bounds: [number, number, number] | null;
  hidden: boolean;
};

export type SupportSurface = {
  id: string;
  center: [number, number, number];
  width: number;
  depth: number;
  confidence: number;
  uncertainty: number;
  evidenceCount: number;
};

const SUPPORT_Y_TOLERANCE = 0.13;
const EXCLUDED_LABEL_PARTS = [
  "person",
  "monitor",
  "whiteboard",
  "wall decoration",
  "picture frame",
  "poster",
];

type MeasuredFootprint = {
  id: string;
  y: number;
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
  confidence: number;
  uncertainty: number;
};

function footprint(entity: SupportEntity): MeasuredFootprint | null {
  if (
    entity.hidden ||
    entity.position === null ||
    entity.bounds === null ||
    entity.presence === "missing" ||
    entity.presence === "archived" ||
    EXCLUDED_LABEL_PARTS.some((part) => entity.label.toLowerCase().includes(part))
  ) {
    return null;
  }
  const stage = toStage(entity.position);
  const extent = toStageExtent(entity.bounds);
  return {
    id: entity.id,
    y: stage[1],
    minX: stage[0] - extent[0] / 2,
    maxX: stage[0] + extent[0] / 2,
    minZ: stage[2] - extent[2] / 2,
    maxZ: stage[2] + extent[2] / 2,
    confidence: entity.confidence,
    uncertainty: entity.uncertainty,
  };
}

/** Infer horizontal tiers from clusters of observed object bottom contacts. */
export function deriveSupportSurfaces(entities: SupportEntity[]): SupportSurface[] {
  const measured = entities
    .map(footprint)
    .filter((item): item is MeasuredFootprint => item !== null)
    .sort((left, right) => left.y - right.y);
  const clusters: MeasuredFootprint[][] = [];
  for (const item of measured) {
    const cluster = clusters.find((candidate) => {
      const meanY = candidate.reduce((sum, value) => sum + value.y, 0) / candidate.length;
      return Math.abs(item.y - meanY) <= SUPPORT_Y_TOLERANCE;
    });
    if (cluster === undefined) {
      clusters.push([item]);
    } else {
      cluster.push(item);
    }
  }

  return clusters.flatMap((cluster, index) => {
    if (cluster.length < 2) {
      return [];
    }
    const minX = Math.min(...cluster.map((item) => item.minX));
    const maxX = Math.max(...cluster.map((item) => item.maxX));
    const minZ = Math.min(...cluster.map((item) => item.minZ));
    const maxZ = Math.max(...cluster.map((item) => item.maxZ));
    const y = cluster.reduce((sum, item) => sum + item.y, 0) / cluster.length;
    const confidence = Math.min(...cluster.map((item) => item.confidence));
    const uncertainty = Math.max(0.25, ...cluster.map((item) => item.uncertainty));
    return [{
      id: `support-${String(index)}-${cluster.map((item) => item.id).join("-")}`,
      center: [(minX + maxX) / 2, y, (minZ + maxZ) / 2] as [number, number, number],
      width: Math.max(0.5, maxX - minX + 0.18),
      depth: Math.max(0.36, maxZ - minZ + 0.18),
      confidence,
      uncertainty,
      evidenceCount: cluster.length,
    }];
  });
}
