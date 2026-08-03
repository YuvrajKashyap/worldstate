/**
 * Camera rig: spherical orbit with drag inertia, wheel zoom, and eased
 * focus jumps. All intents flow through cameraBus so keyboard shortcuts
 * and HoloConsole gestures steer the identical rig.
 */

import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import * as THREE from "three";

import { cameraBus } from "../../lib/world/cameraBus";

const ROTATE_SPEED = 0.0052;
const INERTIA_DECAY = 0.93;

export function CameraRig({ reducedMotion }: { reducedMotion: boolean }) {
  const { camera, gl } = useThree();
  const current = useRef({
    theta: cameraBus.read().theta,
    phi: cameraBus.read().phi,
    radius: cameraBus.read().radius,
    target: new THREE.Vector3(...cameraBus.read().target),
  });
  const velocity = useRef({ theta: 0, phi: 0 });
  const dragging = useRef(false);
  const lastPointer = useRef({ x: 0, y: 0 });

  useEffect(() => {
    const element = gl.domElement;

    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0) {
        return;
      }
      dragging.current = true;
      velocity.current = { theta: 0, phi: 0 };
      lastPointer.current = { x: event.clientX, y: event.clientY };
      element.setPointerCapture(event.pointerId);
    };
    const onPointerMove = (event: PointerEvent) => {
      if (!dragging.current) {
        return;
      }
      const dx = event.clientX - lastPointer.current.x;
      const dy = event.clientY - lastPointer.current.y;
      lastPointer.current = { x: event.clientX, y: event.clientY };
      cameraBus.orbit(-dx * ROTATE_SPEED, -dy * ROTATE_SPEED);
      velocity.current = {
        theta: -dx * ROTATE_SPEED,
        phi: -dy * ROTATE_SPEED,
      };
    };
    const endDrag = (event: PointerEvent) => {
      if (dragging.current && element.hasPointerCapture(event.pointerId)) {
        element.releasePointerCapture(event.pointerId);
      }
      dragging.current = false;
    };
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      cameraBus.zoom(event.deltaY > 0 ? 1.09 : 0.92);
    };

    element.addEventListener("pointerdown", onPointerDown);
    element.addEventListener("pointermove", onPointerMove);
    element.addEventListener("pointerup", endDrag);
    element.addEventListener("pointercancel", endDrag);
    element.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      element.removeEventListener("pointerdown", onPointerDown);
      element.removeEventListener("pointermove", onPointerMove);
      element.removeEventListener("pointerup", endDrag);
      element.removeEventListener("pointercancel", endDrag);
      element.removeEventListener("wheel", onWheel);
    };
  }, [gl]);

  useFrame((_, delta) => {
    // Drag inertia keeps the world spinning briefly after release.
    if (!dragging.current && !reducedMotion) {
      const spin = velocity.current;
      if (Math.abs(spin.theta) > 1e-5 || Math.abs(spin.phi) > 1e-5) {
        cameraBus.orbit(spin.theta, spin.phi);
        const decay = Math.pow(INERTIA_DECAY, delta * 60);
        spin.theta *= decay;
        spin.phi *= decay;
      }
    }

    const intent = cameraBus.read();
    const state = current.current;
    const ease = reducedMotion ? 1 : 1 - Math.exp(-delta * 7.5);
    state.theta += (intent.theta - state.theta) * ease;
    state.phi += (intent.phi - state.phi) * ease;
    state.radius += (intent.radius - state.radius) * ease;
    state.target.x += (intent.target[0] - state.target.x) * ease;
    state.target.y += (intent.target[1] - state.target.y) * ease;
    state.target.z += (intent.target[2] - state.target.z) * ease;

    const sinPhi = Math.sin(state.phi);
    camera.position.set(
      state.target.x + state.radius * sinPhi * Math.sin(state.theta),
      state.target.y + state.radius * Math.cos(state.phi),
      state.target.z + state.radius * sinPhi * Math.cos(state.theta),
    );
    camera.lookAt(state.target);
  });

  return null;
}
