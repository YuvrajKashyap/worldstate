/**
 * The world viewport. Renders the 3D memory volume when WebGL is available
 * and a fully functional top-down instrument map when it is not.
 */

import { Canvas, useFrame } from "@react-three/fiber";
import {
  Bloom,
  EffectComposer,
  Vignette,
} from "@react-three/postprocessing";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";

import { palette } from "../../lib/palette";
import { cameraBus } from "../../lib/world/cameraBus";
import { toStage } from "../../lib/world/space";
import { deriveSupportSurfaces } from "../../lib/world/supportSurfaces";
import { useUiStore } from "../../state/uiStore";
import { useWorldStore } from "../../state/worldStore";
import { CameraRig } from "./CameraRig";
import {
  EntityLayer,
  GhostLayer,
  PulseLayer,
  SceneGraphLayer,
} from "./Entities";
import { FlatMap } from "./FlatMap";
import { MemoryVolume } from "./MemoryVolume";
import { SupportSurfaceLayer } from "./SupportSurfaces";
import { useViewData } from "./useViewData";

function supportsWebGl(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return (
      canvas.getContext("webgl2") !== null ||
      canvas.getContext("webgl") !== null
    );
  } catch {
    return false;
  }
}

function BootDriver({
  bootProgressRef,
  reducedMotion,
}: {
  bootProgressRef: React.RefObject<number>;
  reducedMotion: boolean;
}) {
  const startedAtRef = useRef<number | null>(null);
  useFrame(({ clock }) => {
    if (reducedMotion) {
      bootProgressRef.current = 1;
      return;
    }
    startedAtRef.current ??= clock.getElapsedTime();
    bootProgressRef.current = Math.min(
      1,
      (clock.getElapsedTime() - startedAtRef.current) / 2.8,
    );
  });
  return null;
}

/** Applies focus requests (double-click, search jumps, holo pinches). */
function FocusDriver() {
  const focusRequest = useUiStore((state) => state.focusRequest);
  useEffect(() => {
    if (focusRequest === null) {
      return;
    }
    const record = useWorldStore.getState().entities[focusRequest.entityId];
    if (record?.position != null) {
      cameraBus.focus(toStage(record.position), 1.9);
    }
  }, [focusRequest]);
  return null;
}

export default function WorldCanvas({
  reducedMotion,
}: {
  reducedMotion: boolean;
}) {
  const webgl = useMemo(() => supportsWebGl(), []);
  const bootProgressRef = useRef(0);
  const view = useViewData();
  const supportSurfaces = useMemo(
    () => deriveSupportSurfaces(view.entities),
    [view.entities],
  );
  const layers = useUiStore((state) => state.layers);
  const select = useUiStore((state) => state.select);

  if (!webgl) {
    return <FlatMap view={view} />;
  }

  return (
    <Canvas
      className="world-canvas"
      dpr={[1, 1.5]}
      camera={{ fov: 46, near: 0.1, far: 40 }}
      gl={{ antialias: true, alpha: false }}
      onPointerMissed={() => {
        select(null);
      }}
      onCreated={({ gl, scene }) => {
        gl.setClearColor(new THREE.Color(palette.blackGlass));
        scene.fog = new THREE.FogExp2(new THREE.Color(palette.blackGlass), 0.025);
      }}
    >
      <BootDriver bootProgressRef={bootProgressRef} reducedMotion={reducedMotion} />
      <CameraRig reducedMotion={reducedMotion} />
      <FocusDriver />
      <MemoryVolume
        bootProgressRef={bootProgressRef}
        reducedMotion={reducedMotion}
        showUncertainty={layers.uncertainty}
      />
      <SupportSurfaceLayer
        surfaces={supportSurfaces}
        showUncertainty={layers.uncertainty}
      />
      <EntityLayer
        entities={view.entities}
        reducedMotion={reducedMotion}
        showLabels={layers.labels}
        showUncertainty={layers.uncertainty}
      />
      {layers.ghosts && <GhostLayer ghosts={view.ghosts} />}
      <PulseLayer pulses={view.pulses} reducedMotion={reducedMotion} />
      {layers.graph && (
        <SceneGraphLayer edges={view.edges} entities={view.entities} />
      )}
      <EffectComposer>
        <Bloom
          intensity={layers.uncertainty ? 0.38 : 0.22}
          luminanceThreshold={0.58}
          luminanceSmoothing={0.24}
          mipmapBlur
        />
        <Vignette eskil={false} offset={0.32} darkness={0.52} />
      </EffectComposer>
    </Canvas>
  );
}
