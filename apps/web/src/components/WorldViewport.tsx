import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

type MemoryVolumeProps = {
  animate: boolean;
};

function deterministicNoise(index: number, axis: number): number {
  const value = Math.sin(index * 12.9898 + axis * 78.233) * 43_758.5453;
  return value - Math.floor(value);
}

function MemoryVolume({ animate }: MemoryVolumeProps) {
  const pointsRef = useRef<THREE.Points>(null);
  const geometry = useMemo(() => {
    const positions = new Float32Array(1_600 * 3);

    for (let index = 0; index < 1_600; index += 1) {
      const offset = index * 3;
      const radius = 0.9 + deterministicNoise(index, 0) * 1.35;
      const theta = deterministicNoise(index, 1) * Math.PI * 2;
      const vertical = (deterministicNoise(index, 2) - 0.5) * 1.6;

      positions[offset] = Math.cos(theta) * radius;
      positions[offset + 1] = vertical;
      positions[offset + 2] = Math.sin(theta) * radius * 0.62;
    }

    const result = new THREE.BufferGeometry();
    result.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    return result;
  }, []);

  useEffect(
    () => () => {
      geometry.dispose();
    },
    [geometry],
  );

  useFrame((_, delta) => {
    if (animate && pointsRef.current !== null) {
      pointsRef.current.rotation.y += delta * 0.055;
    }
  });

  return (
    <points ref={pointsRef} geometry={geometry}>
      <pointsMaterial
        color="#b5f2e7"
        opacity={0.72}
        size={0.022}
        sizeAttenuation
        transparent
      />
    </points>
  );
}

export default function WorldViewport() {
  const reducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)",
  ).matches;

  return (
    <section className="viewport" aria-labelledby="empty-scene-title">
      <Canvas
        camera={{ position: [0, 0.4, 4.8], fov: 42 }}
        dpr={[1, 1.5]}
        gl={{ antialias: true, powerPreference: "high-performance" }}
      >
        <color attach="background" args={["#08100f"]} />
        <fog attach="fog" args={["#08100f", 3.6, 7.8]} />
        <MemoryVolume animate={!reducedMotion} />
      </Canvas>
      <div className="viewport__reticle" aria-hidden="true" />
      <div className="viewport__copy">
        <p className="eyebrow">Memory volume</p>
        <h1 id="empty-scene-title">No scene active</h1>
        <p>Start with a camera observation or a short spatial scan.</p>
      </div>
    </section>
  );
}
