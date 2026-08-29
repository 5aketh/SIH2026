import React, { useRef, useMemo } from "react";
import { useFrame } from "@react-three/fiber";
import { useTexture } from "@react-three/drei";
import * as THREE from "three";
import vertexShader from "../shaders/globeVertexShader.glsl?raw";
import fragmentShader from "../shaders/globeFragmentShader.glsl?raw";

export default function MorphingGlobeMesh({ targetProgress }) {
  const meshRef = useRef();
  
  const [dayMap, bumpMap] = useTexture([
    "https://cdn.jsdelivr.net/npm/three-globe/example/img/earth-blue-marble.jpg",
    "https://cdn.jsdelivr.net/gh/mrdoob/three.js@dev/examples/textures/planets/earth_normal_2048.jpg",
  ]);

  const uniforms = useMemo(
    () => ({
      uProgress: { value: 0 },
      uDayMap: { value: dayMap },
      uBumpMap: { value: bumpMap },
      uSunDirection: { value: new THREE.Vector3(8, 8, 6) },
    }),
    [dayMap, bumpMap]
  );

  const geometry = useMemo(() => {
    const R = 3.0;
    return new THREE.PlaneGeometry(2.0 * Math.PI * R, Math.PI * R, 360, 180);
  }, []);

  useFrame((state, delta) => {
    if (meshRef.current) {
      meshRef.current.material.uniforms.uProgress.value = THREE.MathUtils.lerp(
        meshRef.current.material.uniforms.uProgress.value,
        targetProgress,
        0.15
      );

      // Rotate globe, but flatten rotation cleanly as progress reaches flat map state
      if (targetProgress > 0.8) {
        meshRef.current.rotation.y = THREE.MathUtils.lerp(meshRef.current.rotation.y, 0, 0.1);
        meshRef.current.rotation.x = THREE.MathUtils.lerp(meshRef.current.rotation.x, 0, 0.1);
      } else {
        meshRef.current.rotation.y += delta * 0.25;
      }
    }
  });

  const atmosOpacity = Math.max(0, 0.04 * (1 - targetProgress * 2));

  return (
    <group>
      {atmosOpacity > 0 && (
        <mesh scale={[1.04, 1.04, 1.04]}>
          <sphereGeometry args={[3.0, 32, 32]} />
          <meshBasicMaterial color="#38bdf8" transparent opacity={atmosOpacity} side={THREE.BackSide} />
        </mesh>
      )}
      <mesh ref={meshRef} geometry={geometry}>
        <shaderMaterial
          vertexShader={vertexShader}
          fragmentShader={fragmentShader}
          uniforms={uniforms}
          side={THREE.DoubleSide}
          depthWrite={true}
          depthTest={true}
        />
      </mesh>
    </group>
  );
}