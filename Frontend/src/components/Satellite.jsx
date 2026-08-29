import React, { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

export default function Satellite({ progress }) {
  const satRef = useRef();

  const panelTexture = useMemo(() => {
    const canvas = document.createElement("canvas");
    canvas.width = 128;
    canvas.height = 128;
    const ctx = canvas.getContext("2d");
    
    ctx.fillStyle = "#f59e0b"; 
    ctx.fillRect(0, 0, 128, 128);
    
    ctx.strokeStyle = "#b45309"; 
    ctx.lineWidth = 6;
    ctx.strokeRect(0, 0, 128, 128);

    ctx.lineWidth = 4;
    ctx.beginPath();
    for (let i = 32; i < 128; i += 32) {
      ctx.moveTo(i, 0);
      ctx.lineTo(i, 128);
    }
    for (let j = 32; j < 128; j += 32) {
      ctx.moveTo(0, j);
      ctx.lineTo(128, j);
    }
    ctx.stroke();

    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(2, 1);
    return texture;
  }, []);

  useFrame((state) => {
    if (!satRef.current) return;
    const t = state.clock.elapsedTime * 0.55;
    const orbitRadius = 4.2;

    const x = Math.cos(t) * orbitRadius;
    const z = Math.sin(t) * orbitRadius;
    const y = Math.sin(t * 0.5) * 1.2;

    satRef.current.position.set(x, y, z);
    satRef.current.rotation.y = -t;
  });

  const opacity = Math.max(0, 1 - progress * 5);
  if (opacity <= 0) return null;

  return (
    <group ref={satRef} scale={[opacity, opacity, opacity]}>
      <mesh castShadow receiveShadow>
        <boxGeometry args={[0.2, 0.1, 0.3]} />
        <meshStandardMaterial color="#475569" metalness={0.8} roughness={0.2} />
      </mesh>
      <mesh position={[0.3, 0, 0]} castShadow receiveShadow>
        <boxGeometry args={[0.4, 0.02, 0.15]} />
        <meshStandardMaterial
          map={panelTexture}
          metalness={0.7}
          roughness={0.3}
          emissive="#d97706"
          emissiveIntensity={0.2}
        />
      </mesh>
      <mesh position={[-0.3, 0, 0]} castShadow receiveShadow>
        <boxGeometry args={[0.4, 0.02, 0.15]} />
        <meshStandardMaterial
          map={panelTexture}
          metalness={0.7}
          roughness={0.3}
          emissive="#d97706"
          emissiveIntensity={0.2}
        />
      </mesh>
      <pointLight color="#e11d48" intensity={0.8} distance={1.5} />
    </group>
  );
}