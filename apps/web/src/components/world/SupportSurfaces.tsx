import { Html } from "@react-three/drei";
import * as THREE from "three";

import type { SupportSurface } from "../../lib/world/supportSurfaces";

export function SupportSurfaceLayer({
  surfaces,
  showUncertainty,
}: {
  surfaces: SupportSurface[];
  showUncertainty: boolean;
}) {
  return (
    <group>
      {surfaces.map((surface, index) => (
        <group key={surface.id} position={surface.center}>
          <mesh rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[surface.width, surface.depth]} />
            <meshBasicMaterial
              color="#73d8cc"
              transparent
              opacity={showUncertainty ? 0.08 : 0.035}
              side={THREE.DoubleSide}
              depthWrite={false}
            />
          </mesh>
          <mesh position={[0, -0.008, 0]}>
            <boxGeometry args={[surface.width, 0.012, surface.depth]} />
            <meshBasicMaterial
              color="#73d8cc"
              transparent
              opacity={0.16 * surface.confidence}
              wireframe
              depthWrite={false}
            />
          </mesh>
          {showUncertainty && (
            <Html
              position={[-surface.width / 2, 0.035, -surface.depth / 2]}
              distanceFactor={5.2}
              style={{ pointerEvents: "none" }}
            >
              <span className="graph-edge-label">
                inferred support {String(index + 1)} · {String(surface.evidenceCount)} contacts
              </span>
            </Html>
          )}
        </group>
      ))}
    </group>
  );
}
