import React, { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";

export default function GeographicMarker({ city, color, progress, showMarkers, onSelectCity }) {
  const markerRef = useRef();

  useFrame(() => {
    if (!markerRef.current) return;
    const R = 3.0;
    const lonRad = (city.lng * Math.PI) / 180;
    const latRad = (city.lat * Math.PI) / 180;

    const t1 = Math.min(Math.max(progress / 0.5, 0), 1);
    const t2 = Math.min(Math.max((progress - 0.5) / 0.5, 0), 1);

    const rLat = R * ((1 - t1) * Math.cos(latRad) + t1 * 1.0);
    const xCyl = rLat * Math.sin(lonRad);
    const yCyl = R * ((1 - t1) * Math.sin(latRad) + t1 * latRad);
    const zCyl = rLat * Math.cos(lonRad);

    let finalX, finalY, finalZ;
    if (progress <= 0.5) {
      finalX = xCyl;
      finalY = yCyl;
      finalZ = zCyl;
    } else {
      const cylEnd = R * Math.sin(lonRad);
      const cylY = R * latRad;
      const cylZ = R * Math.cos(lonRad);

      finalX = (1 - t2) * cylEnd + t2 * (R * lonRad);
      finalY = cylY;
      finalZ = (1 - t2) * cylZ;
    }

    markerRef.current.position.set(finalX, finalY, finalZ + 0.05);
  });

  if (!showMarkers || progress < 0.95) return null;

  return (
    <group ref={markerRef}>
      <mesh onClick={(e) => { e.stopPropagation(); onSelectCity(city); }} style={{ cursor: "pointer" }}>
        <sphereGeometry args={[0.08, 16, 16]} />
        <meshBasicMaterial color={color} />
      </mesh>
      <mesh scale={[1.8, 1.8, 1.8]}>
        <ringGeometry args={[0.08, 0.12, 16]} />
        <meshBasicMaterial color={color} transparent opacity={0.6} side={THREE.DoubleSide} />
      </mesh>

      <Html position={[0, 0.18, 0]} center distanceFactor={10}>
        <div
          onClick={() => onSelectCity(city)}
          style={{
            cursor: "pointer",
            backgroundColor: "rgba(15, 23, 42, 0.95)",
            backdropFilter: "blur(6px)",
            border: `1px solid ${color}`,
            borderRadius: "6px",
            padding: "4px 8px",
            color: "#f8fafc",
            fontFamily: "system-ui, sans-serif",
            whiteSpace: "nowrap",
            boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
          }}
        >
          <div style={{ fontSize: "11px", fontWeight: 700, color: color }}>{city.name}</div>
        </div>
      </Html>
    </group>
  );
}