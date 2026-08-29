import React, { useRef, useMemo } from "react";
import * as THREE from "three";

export default function GlobeShadow({ progress }) {
  const shadowRef = useRef();

  const shadowTexture = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 256;
    const ctx = canvas.getContext("2d");
    const gradient = ctx.createRadialGradient(128, 128, 0, 128, 128, 128);
    gradient.addColorStop(0, "rgba(30, 41, 59, 0.35)");
    gradient.addColorStop(0.4, "rgba(30, 41, 59, 0.1)");
    gradient.addColorStop(1, "rgba(30, 41, 59, 0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 256, 256);
    return new THREE.CanvasTexture(canvas);
  }, []);

  if (progress > 0.01) return null;

  return (
    <mesh
      ref={shadowRef}
      position={[0.2, -3.2, -0.4]}
      rotation={[-Math.PI / 2.2, 0, 0]}
      scale={[4.8, 4.8, 1]}
    >
      <planeGeometry args={[3, 3]} />
      <meshBasicMaterial
        map={shadowTexture}
        transparent={true}
        depthWrite={false}
      />
    </mesh>
  );
}