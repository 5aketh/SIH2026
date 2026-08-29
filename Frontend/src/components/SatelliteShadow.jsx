import React, { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

export default function SatelliteShadow({ progress }) {
  const shadowRef = useRef();

  const shadowTexture = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 64;
    canvas.height = 32;
    const ctx = canvas.getContext("2d");
    const gradient = ctx.createRadialGradient(32, 16, 0, 32, 16, 32);
    gradient.addColorStop(0, "rgba(15, 23, 42, 0.18)");
    gradient.addColorStop(1, "rgba(15, 23, 42, 0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 64, 32);
    return new THREE.CanvasTexture(canvas);
  }, []);

  useFrame((state) => {
    if (!shadowRef.current) return;
    const t = state.clock.elapsedTime * 0.55;
    const orbitRadius = 4.2;
    const x = Math.cos(t) * orbitRadius;
    const z = Math.sin(t) * orbitRadius;

    shadowRef.current.position.set(x - 0.3, -3.2, z);
  });

  const opacity = Math.max(0, 1 - progress * 5);
  if (opacity <= 0) return null;

  return (
    <mesh ref={shadowRef} rotation={[-Math.PI / 2, 0, 0]} scale={[1.4, 0.8, 1]}>
      <planeGeometry args={[1.0, 0.5]} />
      <meshBasicMaterial map={shadowTexture} transparent={true} depthWrite={false} />
    </mesh>
  );
}