/**
 * Entity holograms with the X-ray Memory grammar:
 * solid = observed, wireframe = occluded, amber pulse = predicted,
 * red ghost = missing, fading = stale/archived. Ghost Mode renders event
 * ghosts; change pulses ring outward in 3D at the event location.
 */

import { Html, QuadraticBezierLine } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { memo, useRef, useState } from "react";
import * as THREE from "three";

import { eventColor, presenceColor, presenceLabel } from "../../lib/palette";
import { projectPosition } from "../../lib/world/prediction";
import { toStage, toStageExtent } from "../../lib/world/space";
import type { GraphEdge } from "../../lib/world/relationships";
import type { GhostMarker, Pulse } from "../../state/worldStore";
import { useUiStore } from "../../state/uiStore";
import type { EntityView } from "./useViewData";

const PULSE_LIFE_MS = 2_400;

function geometryFor(label: string): THREE.BufferGeometry {
  const lower = label.toLowerCase();
  if (lower.includes("cup") || lower.includes("mug") || lower.includes("bottle")) {
    return new THREE.CylinderGeometry(0.09, 0.075, 0.17, 18, 1);
  }
  if (lower.includes("book") || lower.includes("notebook")) {
    return new THREE.BoxGeometry(0.24, 0.045, 0.17);
  }
  if (lower.includes("phone")) {
    return new THREE.BoxGeometry(0.075, 0.015, 0.15);
  }
  if (lower.includes("laptop") || lower.includes("keyboard")) {
    return new THREE.BoxGeometry(0.32, 0.02, 0.22);
  }
  return new THREE.IcosahedronGeometry(0.1, 0);
}

const geometryCache = new Map<
  string,
  { solid: THREE.BufferGeometry; edges: THREE.EdgesGeometry; baseSize: THREE.Vector3 }
>();

function cachedGeometry(label: string) {
  const key = label.toLowerCase();
  let entry = geometryCache.get(key);
  if (entry === undefined) {
    const solid = geometryFor(label);
    solid.computeBoundingBox();
    const baseSize = solid.boundingBox?.getSize(new THREE.Vector3()) ?? new THREE.Vector3(1, 1, 1);
    entry = { solid, edges: new THREE.EdgesGeometry(solid, 12), baseSize };
    geometryCache.set(key, entry);
  }
  return entry;
}

const shellGeometry = (() => {
  const count = 110;
  const positions = new Float32Array(count * 3);
  for (let i = 0; i < count; i += 1) {
    const u = Math.random();
    const v = Math.random();
    const theta = 2 * Math.PI * u;
    const phi = Math.acos(2 * v - 1);
    const radius = 0.16 + Math.random() * 0.1;
    positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
    positions[i * 3 + 2] = radius * Math.cos(phi);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  return geometry;
})();

type HologramProps = {
  view: EntityView;
  reducedMotion: boolean;
  showLabels: boolean;
  showUncertainty: boolean;
};

const EntityHologram = memo(function EntityHologram({
  view,
  reducedMotion,
  showLabels,
  showUncertainty,
}: HologramProps) {
  const group = useRef<THREE.Group>(null);
  const fillMaterial = useRef<THREE.MeshBasicMaterial>(null);
  const edgeMaterial = useRef<THREE.LineBasicMaterial>(null);
  const shellMaterial = useRef<THREE.PointsMaterial>(null);
  const shellPoints = useRef<THREE.Points>(null);
  const scaleState = useRef({ value: reducedMotion ? 1 : 0.01, velocity: 0 });
  const [hovered, setHovered] = useState(false);
  const select = useUiStore((state) => state.select);
  const requestFocus = useUiStore((state) => state.requestFocus);

  const { solid, edges, baseSize } = cachedGeometry(view.label);
  const color = presenceColor[view.presence];
  const measuredExtent = view.bounds === null ? null : toStageExtent(view.bounds);
  const baseScale: [number, number, number] = measuredExtent === null
    ? [1, 1, 1]
    : [
        measuredExtent[0] / Math.max(0.001, baseSize.x),
        measuredExtent[1] / Math.max(0.001, baseSize.y),
        measuredExtent[2] / Math.max(0.001, baseSize.z),
      ];
  const target = view.position === null
    ? null
    : (() => {
        const support = toStage(view.position);
        return [
          support[0],
          support[1] + (measuredExtent?.[1] ?? 0) / 2,
          support[2],
        ] as [number, number, number];
      })();

  useFrame(({ clock }, delta) => {
    const node = group.current;
    const position = view.position;
    if (node === null || target === null || position === null) {
      return;
    }
    const t = clock.getElapsedTime();
    const projected = projectPosition(
      position,
      view.positionVelocity,
      view.observedAt ?? Date.now(),
      Date.now(),
    );
    const predictedTarget = toStage(projected);
    predictedTarget[1] += (measuredExtent?.[1] ?? 0) / 2;
    const ease = 1 - Math.exp(-delta * 9);
    node.position.x += (predictedTarget[0] - node.position.x) * ease;
    node.position.y += (predictedTarget[1] - node.position.y) * ease;
    node.position.z += (predictedTarget[2] - node.position.z) * ease;

    // Spring scale-in with slight overshoot (skipped under reduced motion).
    const spring = scaleState.current;
    if (reducedMotion) {
      spring.value = 1;
    } else {
      spring.velocity += (1 - spring.value) * 110 * delta;
      spring.velocity *= Math.exp(-9 * delta);
      spring.value += spring.velocity * delta;
    }
    const emphasis = view.selected || hovered ? 1.12 : 1;
    const animatedScale = Math.max(0.01, spring.value) * emphasis;
    node.scale.set(
      baseScale[0] * animatedScale,
      baseScale[1] * animatedScale,
      baseScale[2] * animatedScale,
    );

    const fill = fillMaterial.current;
    const edge = edgeMaterial.current;
    if (fill === null || edge === null) {
      return;
    }
    let fillOpacity = 0.16;
    let edgeOpacity = 0.95;
    switch (view.presence) {
      case "visible":
      case "rediscovered":
        fillOpacity = 0.2;
        break;
      case "occluded":
        fillOpacity = 0.03;
        edgeOpacity = 0.8;
        break;
      case "predicted":
        fillOpacity = reducedMotion
          ? 0.14
          : 0.1 + 0.1 * (0.5 + 0.5 * Math.sin(t * 2.6));
        edgeOpacity = reducedMotion
          ? 0.7
          : 0.5 + 0.35 * (0.5 + 0.5 * Math.sin(t * 2.6));
        break;
      case "missing":
        fillOpacity = reducedMotion
          ? 0.12
          : 0.08 + 0.06 * (0.5 + 0.5 * Math.sin(t * 9.0));
        edgeOpacity = reducedMotion
          ? 0.55
          : 0.4 + 0.25 * (0.5 + 0.5 * Math.sin(t * 9.0));
        break;
      case "archived":
        fillOpacity = 0.04;
        edgeOpacity = 0.25;
        break;
    }
    const confidenceDim = 0.55 + view.confidence * 0.45;
    const staleDim = view.stale ? 0.45 : 1;
    fill.opacity = fillOpacity * staleDim;
    edge.opacity = edgeOpacity * confidenceDim * staleDim;

    const shell = shellMaterial.current;
    if (shell !== null) {
      const wantShell =
        showUncertainty && (view.uncertainty > 0.3 || view.stale);
      shell.opacity = wantShell
        ? Math.min(0.75, view.uncertainty * 0.8 + (view.stale ? 0.2 : 0))
        : 0;
      if (shellPoints.current !== null && !reducedMotion) {
        shellPoints.current.rotation.y = t * 0.4;
        shellPoints.current.rotation.x = t * 0.13;
      }
    }
  });

  if (target === null || view.hidden) {
    return null;
  }

  return (
    <group
      ref={group}
      position={target}
      onClick={(event) => {
        event.stopPropagation();
        select(view.id);
      }}
      onDoubleClick={(event) => {
        event.stopPropagation();
        requestFocus(view.id);
      }}
      onPointerOver={(event) => {
        event.stopPropagation();
        setHovered(true);
        document.body.style.cursor = "pointer";
      }}
      onPointerOut={() => {
        setHovered(false);
        document.body.style.cursor = "";
      }}
    >
      <mesh geometry={solid}>
        <meshBasicMaterial
          ref={fillMaterial}
          color={color}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </mesh>
      <lineSegments geometry={edges}>
        <lineBasicMaterial
          ref={edgeMaterial}
          color={color}
          transparent
          depthWrite={false}
        />
      </lineSegments>
      <points ref={shellPoints} geometry={shellGeometry}>
        <pointsMaterial
          ref={shellMaterial}
          color={presenceColor[view.stale ? "archived" : view.presence]}
          size={0.014}
          transparent
          opacity={0}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
      {view.selected && (
        <mesh
          rotation={[-Math.PI / 2, 0, 0]}
          position={[0, measuredExtent === null ? -target[1] + 0.012 : -measuredExtent[1] / 2 + 0.012, 0]}
        >
          <ringGeometry args={[0.19, 0.21, 48]} />
          <meshBasicMaterial
            color={color}
            transparent
            opacity={0.85}
            side={THREE.DoubleSide}
            depthWrite={false}
          />
        </mesh>
      )}
      {(showLabels || view.selected || hovered) && (
        <Html
          position={[0, (measuredExtent?.[1] ?? 0.28) / 2 + 0.1, 0]}
          center
          distanceFactor={4.4}
          style={{ pointerEvents: "none" }}
          zIndexRange={[40, 0]}
        >
          <div
            className={`entity-tag entity-tag--${view.presence}${view.selected ? " entity-tag--selected" : ""}`}
          >
            <span className="entity-tag__name">{view.label}</span>
            <span className="entity-tag__meta">
              {presenceLabel[view.presence]} ·{" "}
              {(view.confidence * 100).toFixed(0)}
            </span>
          </div>
        </Html>
      )}
    </group>
  );
});

function PulseRing({ pulse, reducedMotion }: { pulse: Pulse; reducedMotion: boolean }) {
  const mesh = useRef<THREE.Mesh>(null);
  const material = useRef<THREE.MeshBasicMaterial>(null);
  const stage = pulse.position !== null ? toStage(pulse.position) : null;

  useFrame(() => {
    const node = mesh.current;
    const mat = material.current;
    if (node === null || mat === null) {
      return;
    }
    const age = (Date.now() - pulse.at) / PULSE_LIFE_MS;
    if (age > 1) {
      node.visible = false;
      return;
    }
    node.visible = true;
    const eased = 1 - Math.pow(1 - Math.min(1, age), 3);
    const scale = reducedMotion ? 1 : 0.2 + eased * 2.2;
    node.scale.setScalar(scale);
    mat.opacity = (1 - age) * 0.8;
  });

  if (stage === null) {
    return null;
  }
  return (
    <mesh
      ref={mesh}
      rotation={[-Math.PI / 2, 0, 0]}
      position={[stage[0], stage[1] + 0.015, stage[2]]}
    >
      <ringGeometry args={[0.28, 0.31, 56]} />
      <meshBasicMaterial
        ref={material}
        color={eventColor[pulse.kind]}
        transparent
        side={THREE.DoubleSide}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </mesh>
  );
}

export function PulseLayer({
  pulses,
  reducedMotion,
}: {
  pulses: Pulse[];
  reducedMotion: boolean;
}) {
  return (
    <group>
      {pulses.map((pulse) => (
        <PulseRing key={pulse.id} pulse={pulse} reducedMotion={reducedMotion} />
      ))}
    </group>
  );
}

function timeAgo(at: number): string {
  const seconds = Math.max(0, Math.round((Date.now() - at) / 1000));
  if (seconds < 60) {
    return `${String(seconds)}s ago`;
  }
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes)}m ${String(seconds % 60)}s ago`;
}

function GhostShape({ ghost }: { ghost: GhostMarker }) {
  const [hovered, setHovered] = useState(false);
  const { edges } = cachedGeometry(ghost.label);
  const stage = toStage(ghost.position);
  const color = eventColor[ghost.kind];
  return (
    <group
      position={stage}
      onPointerOver={(event) => {
        event.stopPropagation();
        setHovered(true);
      }}
      onPointerOut={() => {
        setHovered(false);
      }}
    >
      <lineSegments geometry={edges}>
        <lineBasicMaterial color={color} transparent opacity={0.32} depthWrite={false} />
      </lineSegments>
      <mesh visible={false}>
        <sphereGeometry args={[0.16, 8, 8]} />
        <meshBasicMaterial />
      </mesh>
      {hovered && (
        <Html position={[0, 0.2, 0]} center distanceFactor={4.4} style={{ pointerEvents: "none" }}>
          <div className="ghost-tip">
            {ghost.kind} · {timeAgo(ghost.at)}
          </div>
        </Html>
      )}
    </group>
  );
}

export function GhostLayer({ ghosts }: { ghosts: GhostMarker[] }) {
  return (
    <group>
      {ghosts.map((ghost) => (
        <GhostShape key={ghost.key} ghost={ghost} />
      ))}
    </group>
  );
}

function GraphLink({
  edge,
  entities,
}: {
  edge: GraphEdge;
  entities: EntityView[];
}) {
  const from = entities.find((entity) => entity.id === edge.from);
  const to = entities.find((entity) => entity.id === edge.to);
  if (from?.position == null || to?.position == null) {
    return null;
  }
  const a = toStage(from.position);
  const b = toStage(to.position);
  const mid: [number, number, number] = [
    (a[0] + b[0]) / 2,
    Math.max(a[1], b[1]) + 0.32,
    (a[2] + b[2]) / 2,
  ];
  return (
    <group>
      <QuadraticBezierLine
        start={a}
        end={b}
        mid={mid}
        color="#a8a0e8"
        lineWidth={1}
        transparent
        opacity={0.28 + edge.confidence * 0.45}
        dashed
        dashScale={8}
        dashSize={0.6}
        gapSize={0.4}
      />
      <Html position={mid} center distanceFactor={5.2} style={{ pointerEvents: "none" }}>
        <span className="graph-edge-label">{edge.kind.replace("_", " ")}</span>
      </Html>
    </group>
  );
}

export function SceneGraphLayer({
  edges,
  entities,
}: {
  edges: GraphEdge[];
  entities: EntityView[];
}) {
  return (
    <group>
      {edges.map((edge) => (
        <GraphLink key={edge.key} edge={edge} entities={entities} />
      ))}
    </group>
  );
}

export function EntityLayer({
  entities,
  reducedMotion,
  showLabels,
  showUncertainty,
}: {
  entities: EntityView[];
  reducedMotion: boolean;
  showLabels: boolean;
  showUncertainty: boolean;
}) {
  return (
    <group>
      {entities.map((view) => (
        <EntityHologram
          key={view.id}
          view={view}
          reducedMotion={reducedMotion}
          showLabels={showLabels}
          showUncertainty={showUncertainty}
        />
      ))}
    </group>
  );
}
