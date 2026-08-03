/**
 * The memory volume: a confidence-aware particle field and a live grid
 * floor. The floor reacts to change events — pulses ripple outward from
 * the exact spot where the world changed. Ambient drift is disabled under
 * reduced motion; functional states (pulse locations) are preserved.
 */

import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

import { palette, eventColor } from "../../lib/palette";
import { toStage } from "../../lib/world/space";
import { useWorldStore } from "../../state/worldStore";

const MAX_PULSES = 6;
const PULSE_LIFE_MS = 2_400;

const gridVertex = /* glsl */ `
  varying vec2 vWorld;
  void main() {
    vec4 world = modelMatrix * vec4(position, 1.0);
    vWorld = world.xz;
    gl_Position = projectionMatrix * viewMatrix * world;
  }
`;

const gridFragment = /* glsl */ `
  uniform float uTime;
  uniform float uBoot;
  uniform vec3 uColor;
  uniform vec3 uPulsePos[${String(MAX_PULSES)}];
  uniform vec3 uPulseColor[${String(MAX_PULSES)}];
  varying vec2 vWorld;

  float gridLine(vec2 coord, float scale) {
    vec2 g = abs(fract(coord * scale - 0.5) - 0.5) / fwidth(coord * scale);
    return 1.0 - min(min(g.x, g.y), 1.0);
  }

  void main() {
    float radius = length(vWorld);
    float fade = smoothstep(3.4, 0.4, radius);
    float bootRing = smoothstep(uBoot * 4.2, uBoot * 4.2 - 0.5, radius);
    float major = gridLine(vWorld, 1.0) * 0.55;
    float minor = gridLine(vWorld, 4.0) * 0.22;
    vec3 color = uColor * (major + minor);
    float alpha = (major + minor) * fade * bootRing;

    // Event pulses: rings expanding from world-change locations.
    for (int i = 0; i < ${String(MAX_PULSES)}; i++) {
      float age = uPulsePos[i].z;
      if (age < 0.0 || age > 1.0) { continue; }
      float d = distance(vWorld, uPulsePos[i].xy);
      float ring = smoothstep(0.09, 0.0, abs(d - age * 1.9));
      float strength = ring * (1.0 - age) * 0.9;
      color += uPulseColor[i] * strength;
      alpha += strength * fade;
    }

    gl_FragColor = vec4(color, alpha * 0.85);
  }
`;

const pointsVertex = /* glsl */ `
  attribute float aSeed;
  uniform float uTime;
  uniform float uBoot;
  uniform float uAmbient;
  varying float vTwinkle;
  varying float vDepth;

  float easeOut(float t) { return 1.0 - pow(1.0 - t, 3.0); }

  void main() {
    float stagger = clamp((uBoot - aSeed * 0.35) / 0.65, 0.0, 1.0);
    float t = easeOut(stagger);
    float swirl = (1.0 - t) * (6.2831 * aSeed + 2.4);
    vec3 p = position;
    float c = cos(swirl); float s = sin(swirl);
    p = vec3(c * p.x - s * p.z, p.y + (1.0 - t) * (1.6 + aSeed), s * p.x + c * p.z);
    p.xz *= mix(2.6, 1.0, t);
    // Ambient breathing drift, zeroed under reduced motion.
    p.y += sin(uTime * 0.4 + aSeed * 12.0) * 0.035 * uAmbient;
    p.x += sin(uTime * 0.22 + aSeed * 31.0) * 0.03 * uAmbient;

    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    vDepth = -mv.z;
    vTwinkle = 0.55 + 0.45 * sin(uTime * (0.6 + aSeed) + aSeed * 40.0);
    gl_PointSize = (0.8 + aSeed * 1.4) * (20.0 / max(vDepth, 0.8)) * t;
    gl_Position = projectionMatrix * mv;
  }
`;

const pointsFragment = /* glsl */ `
  uniform vec3 uColor;
  uniform float uAmbient;
  uniform float uOpacity;
  varying float vTwinkle;
  varying float vDepth;
  void main() {
    vec2 uv = gl_PointCoord - 0.5;
    float d = length(uv);
    float core = smoothstep(0.5, 0.05, d);
    float twinkle = mix(0.75, vTwinkle, uAmbient);
    float alpha = core * twinkle * smoothstep(9.0, 2.5, vDepth) * uOpacity;
    gl_FragColor = vec4(uColor, alpha);
  }
`;

type MemoryVolumeProps = {
  bootProgressRef: React.RefObject<number>;
  reducedMotion: boolean;
  showUncertainty: boolean;
};

export function MemoryVolume({
  bootProgressRef,
  reducedMotion,
  showUncertainty,
}: MemoryVolumeProps) {
  const gridMaterial = useRef<THREE.ShaderMaterial>(null);
  const pointsMaterial = useRef<THREE.ShaderMaterial>(null);

  const gridUniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uBoot: { value: 0 },
      uColor: { value: new THREE.Color(palette.lumen).multiplyScalar(0.5) },
      uPulsePos: {
        value: Array.from(
          { length: MAX_PULSES },
          () => new THREE.Vector3(0, 0, -1),
        ),
      },
      uPulseColor: {
        value: Array.from({ length: MAX_PULSES }, () => new THREE.Color(0)),
      },
    }),
    [],
  );

  const pointsUniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uBoot: { value: 0 },
      uAmbient: { value: reducedMotion ? 0 : 1 },
      uOpacity: { value: 0.04 },
      uColor: { value: new THREE.Color(palette.lumen) },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- uniforms are mutated in-place each frame
    [],
  );

  const pointsGeometry = useMemo(() => {
    const count = 720;
    const positions = new Float32Array(count * 3);
    const seeds = new Float32Array(count);
    for (let i = 0; i < count; i += 1) {
      const angle = Math.random() * Math.PI * 2;
      const radius = Math.sqrt(Math.random()) * 3.1;
      positions[i * 3] = Math.cos(angle) * radius;
      positions[i * 3 + 1] = Math.pow(Math.random(), 2.2) * 1.7 + 0.02;
      positions[i * 3 + 2] = Math.sin(angle) * radius;
      seeds[i] = Math.random();
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute("aSeed", new THREE.BufferAttribute(seeds, 1));
    return geometry;
  }, []);

  useFrame(({ clock }) => {
    const t = clock.getElapsedTime();
    const boot = bootProgressRef.current;
    if (gridMaterial.current !== null) {
      const uniforms = gridMaterial.current.uniforms;
      (uniforms.uTime as { value: number }).value = t;
      (uniforms.uBoot as { value: number }).value = boot;
      const now = Date.now();
      const pulses = useWorldStore.getState().pulses;
      const positions = (uniforms.uPulsePos as { value: THREE.Vector3[] }).value;
      const colors = (uniforms.uPulseColor as { value: THREE.Color[] }).value;
      let slot = 0;
      for (let i = pulses.length - 1; i >= 0 && slot < MAX_PULSES; i -= 1) {
        const pulse = pulses[i];
        if (pulse?.position == null) {
          continue;
        }
        const age = (now - pulse.at) / PULSE_LIFE_MS;
        if (age > 1) {
          continue;
        }
        const stage = toStage(pulse.position);
        positions[slot]?.set(stage[0], stage[2], reducedMotion ? Math.min(age * 3, 1) : age);
        colors[slot]?.set(eventColor[pulse.kind]);
        slot += 1;
      }
      for (; slot < MAX_PULSES; slot += 1) {
        positions[slot]?.setZ(-1);
      }
    }
    if (pointsMaterial.current !== null) {
      const uniforms = pointsMaterial.current.uniforms;
      (uniforms.uTime as { value: number }).value = t;
      (uniforms.uBoot as { value: number }).value = boot;
      (uniforms.uAmbient as { value: number }).value = reducedMotion ? 0 : 1;
      (uniforms.uOpacity as { value: number }).value = showUncertainty
        ? 0.2
        : 0.025;
    }
  });

  return (
    <group>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]}>
        <planeGeometry args={[8, 8, 1, 1]} />
        <shaderMaterial
          ref={gridMaterial}
          vertexShader={gridVertex}
          fragmentShader={gridFragment}
          uniforms={gridUniforms}
          transparent
          depthWrite={false}
        />
      </mesh>
      <points geometry={pointsGeometry} frustumCulled={false}>
        <shaderMaterial
          ref={pointsMaterial}
          vertexShader={pointsVertex}
          fragmentShader={pointsFragment}
          uniforms={pointsUniforms}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
        />
      </points>
    </group>
  );
}
