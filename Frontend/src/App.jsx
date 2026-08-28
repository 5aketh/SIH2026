import React, { useRef, useState, useMemo, useEffect } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { OrbitControls, useTexture, Html } from "@react-three/drei";
import * as THREE from "three";
import { Flame, ChevronDown, MapPin, X } from "lucide-react";

// --- Geographic Points in "Colour: Points" Format ---
const COLOR_POINTS_DATA = [
  {
    color: "#0284c7", // Deep Sky Blue Accent
    points: [
      { name: "New York", lat: 40.7128, lng: -74.006, country: "United States", population: "8.8M", desc: "Global financial and cultural hub." },
      { name: "Tokyo", lat: 35.6762, lng: 139.6503, country: "Japan", population: "14.0M", desc: "A bustling metropolis blending ultra-modern and traditional." },
    ],
  },
  {
    color: "#e11d48", // Vibrant Rose Accent
    points: [
      { name: "London", lat: 51.5074, lng: -0.1278, country: "United Kingdom", population: "9.0M", desc: "Historic capital with deep global influence." },
      { name: "Sydney", lat: -33.8688, lng: 151.2093, country: "Australia", population: "5.3M", desc: "Famous for its sweeping harbor and iconic opera house." },
    ],
  },
  {
    color: "#059669", // Emerald Accent
    points: [
      { name: "Rio de Janeiro", lat: -22.9068, lng: -43.1729, country: "Brazil", population: "6.7M", desc: "Renowned for beaches, music, and dramatic mountains." },
      { name: "Cairo", lat: 30.0444, lng: 31.2357, country: "Egypt", population: "10.0M", desc: "Sprawling capital set along the historic Nile River." },
    ],
  },
];

// --- Custom GPU GLSL Shaders (Lighter Shades & Softer Lighting) ---

const vertexShader = `
  uniform float uProgress;
  varying vec2 vUv;
  varying vec3 vNormal;

  #define PI 3.1415926535897932384626433832795

  void main() {
    vUv = uv;
    float R = 3.0; // Globe radius
    
    float lon = (uv.x - 0.5) * 2.0 * PI;
    float lat = (uv.y - 0.5) * PI;

    // Stage 1: Sphere -> Cylinder
    float t1 = clamp(uProgress / 0.5, 0.0, 1.0);
    float rLat = R * mix(cos(lat), 1.0, t1);
    vec3 posCylinder = vec3(
      rLat * sin(lon),
      R * mix(sin(lat), lat, t1),
      rLat * cos(lon)
    );

    // Stage 2: Cylinder -> Flat Equirectangular Map
    float t2 = clamp((uProgress - 0.5) / 0.5, 0.0, 1.0);
    vec3 posUnrolling = vec3(
      R * mix(sin(lon), lon, t2),
      R * lat,
      R * cos(lon) * (1.0 - t2)
    );

    vec3 finalPos = mix(posCylinder, posUnrolling, t2);

    // Normal Interpolation
    vec3 nSphere = normalize(vec3(cos(lat) * sin(lon), sin(lat), cos(lat) * cos(lon)));
    vec3 nPlane = vec3(0.0, 0.0, 1.0);
    vNormal = normalize(normalMatrix * mix(nSphere, nPlane, uProgress));

    gl_Position = projectionMatrix * modelViewMatrix * vec4(finalPos, 1.0);
  }
`;

const fragmentShader = `
  uniform sampler2D uDayMap;
  uniform vec3 uSunDirection;
  uniform float uProgress;

  varying vec2 vUv;
  varying vec3 vNormal;

  void main() {
    vec4 texColor = texture2D(uDayMap, vUv);
    
    // Lighter, brighter, and softer color tuning
    float luminance = dot(texColor.rgb, vec3(0.299, 0.587, 0.114));
    vec3 enhancedColor = texColor.rgb;
    
    if (luminance < 0.22) {
      // Much lighter, softer blue ocean tones instead of deep dark navy
      enhancedColor = mix(vec3(0.15, 0.32, 0.52), texColor.rgb * 1.35, 0.6);
    } else {
      // Brighter, more illuminated land tones
      enhancedColor = texColor.rgb * 1.45; 
    }

    vec3 norm = normalize(vNormal);
    // Higher minimum diffuse lighting to prevent harsh dark shadows
    float diff = max(dot(norm, normalize(uSunDirection)), 0.55);

    vec3 baseColor = enhancedColor * (diff + 0.35);
    
    // Grid overlay for flat map mode
    float gridX = step(0.994, fract(vUv.x * 24.0)) + step(0.994, fract(vUv.y * 12.0));
    vec3 gridColor = vec3(0.4, 0.8, 1.0) * gridX * 0.12 * smoothstep(0.6, 1.0, uProgress);

    gl_FragColor = vec4(baseColor + gridColor, 1.0);
  }
`;

// --- Orbiting Satellite Component (Slower speed) ---

function Satellite({ progress }) {
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
    const t = state.clock.elapsedTime * 0.55; // Slowed down from 1.2 to 0.55
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

// --- Shape-Fitted Satellite Shadow (Matching slower speed) ---

function SatelliteShadow({ progress }) {
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
    const t = state.clock.elapsedTime * 0.55; // Synced with satellite speed (0.55)
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

// --- Procedural Globe Shadow ---

function GlobeShadow({ progress }) {
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

// --- Morphing Mesh Component ---

function MorphingGlobeMesh({ targetProgress }) {
  const meshRef = useRef();
  
  const [dayMap, bumpMap] = useTexture([
    "https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg",
    "https://raw.githubusercontent.com/mrdoob/three.js/master/examples/textures/planets/earth_normal_2048.jpg",
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
        0.2
      );

      if (targetProgress < 0.1) {
        meshRef.current.rotation.y += delta * 0.3;
      } else {
        meshRef.current.rotation.y = THREE.MathUtils.lerp(meshRef.current.rotation.y, 0, 0.2);
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
        />
      </mesh>
    </group>
  );
}

// --- Geographic Marker Component ---

function GeographicMarker({ city, color, progress, showMarkers, onSelectCity }) {
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

  if (!showMarkers || progress < 0.99) return null;

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

// --- Main Component ---

export default function ScrollUnwrappingGlobeColorPoints() {
  const [scrollProgress, setScrollProgress] = useState(0);
  const [selectedCity, setSelectedCity] = useState(null);
  const [markersReady, setMarkersReady] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(null);
  const containerRef = useRef();

  // 1-Second Delay Handler after Map is Active
  useEffect(() => {
    let timeout = null;

    if (scrollProgress >= 0.99) {
      setSecondsLeft(1);
      timeout = setTimeout(() => {
        setMarkersReady(true);
        setSecondsLeft(null);
      }, 1000);
    } else {
      setMarkersReady(false);
      setSecondsLeft(null);
    }

    return () => {
      clearTimeout(timeout);
    };
  }, [scrollProgress]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleWheel = (e) => {
      e.preventDefault();
      e.stopPropagation();
      setScrollProgress((prev) => {
        const next = prev + e.deltaY * 0.0025;
        return Math.min(Math.max(next, 0), 1);
      });
    };

    let touchStartY = 0;
    const handleTouchStart = (e) => {
      touchStartY = e.touches[0].clientY;
    };
    const handleTouchMove = (e) => {
      const deltaY = touchStartY - e.touches[0].clientY;
      touchStartY = e.touches[0].clientY;
      setScrollProgress((prev) => {
        const next = prev + deltaY * 0.006;
        return Math.min(Math.max(next, 0), 1);
      });
    };

    container.addEventListener("wheel", handleWheel, { passive: false, capture: true });
    container.addEventListener("touchstart", handleTouchStart, { passive: true });
    container.addEventListener("touchmove", handleTouchMove, { passive: true });

    return () => {
      container.removeEventListener("wheel", handleWheel, { capture: true });
      container.removeEventListener("touchstart", handleTouchStart);
      container.removeEventListener("touchmove", handleTouchMove);
    };
  }, []);

  return (
    <>
      <style>{`
        html, body {
          margin: 0;
          padding: 0;
          width: 100vw;
          height: 100vh;
          overflow: hidden;
          background-color: #f8fafc;
        }
        * {
          box-sizing: border-box;
        }
      `}</style>

      <div
        ref={containerRef}
        style={{
          width: "100vw",
          height: "100vh",
          backgroundColor: "#ffffff",
          position: "fixed",
          top: 0,
          left: 0,
          overflow: "hidden",
        }}
      >
        {/* Fullscreen Canvas */}
        <div style={{ position: "absolute", top: 0, left: 0, width: "100vw", height: "100vh", zIndex: 1 }}>
          <Canvas camera={{ position: [0, 0, 13.5], fov: 45 }} style={{ width: "100%", height: "100%" }}>
            <ambientLight intensity={0.85} />
            <directionalLight position={[8, 10, 8]} intensity={1.3} />

            {/* Globe Soft Shadow */}
            <GlobeShadow progress={scrollProgress} />

            {/* Satellite Soft Shadow */}
            <SatelliteShadow progress={scrollProgress} />

            <React.Suspense fallback={null}>
              <MorphingGlobeMesh targetProgress={scrollProgress} />
              <Satellite progress={scrollProgress} />
              {COLOR_POINTS_DATA.map((group, groupIdx) =>
                group.points.map((city, cityIdx) => (
                  <GeographicMarker
                    key={`${groupIdx}-${cityIdx}`}
                    city={city}
                    color={group.color}
                    progress={scrollProgress}
                    showMarkers={markersReady}
                    onSelectCity={setSelectedCity}
                  />
                ))
              )}
            </React.Suspense>
            <OrbitControls enablePan={true} enableZoom={false} minDistance={4.5} maxDistance={22} />
          </Canvas>
        </div>

        {/* Selected City Pop-up Modal */}
        {selectedCity && (
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: "50%",
              transform: "translate(-50%, -50%)",
              zIndex: 100,
              backgroundColor: "rgba(15, 23, 42, 0.95)",
              backdropFilter: "blur(16px)",
              border: "1px solid rgba(56, 189, 248, 0.3)",
              borderRadius: "16px",
              padding: "24px",
              width: "320px",
              color: "#f8fafc",
              fontFamily: "system-ui, sans-serif",
              boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.25)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <MapPin size={18} color="#38bdf8" />
                <h3 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0, color: "#f8fafc" }}>
                  {selectedCity.name}
                </h3>
              </div>
              <button
                onClick={() => setSelectedCity(null)}
                style={{ background: "none", border: "none", color: "#94a3b8", cursor: "pointer", padding: "4px" }}
              >
                <X size={18} />
              </button>
            </div>
            <div style={{ fontSize: "12px", color: "#38bdf8", fontWeight: 600, marginBottom: "8px" }}>
              {selectedCity.country}
            </div>
            <p style={{ fontSize: "13px", color: "#cbd5e1", lineHeight: "1.5", margin: "0 0 16px 0" }}>
              {selectedCity.desc}
            </p>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: "12px", color: "#94a3b8", borderTop: "1px solid rgba(255,255,255,0.1)", paddingTop: "12px" }}>
              <span>Population: <strong>{selectedCity.population}</strong></span>
              <span>Coords: {selectedCity.lat}°, {selectedCity.lng}°</span>
            </div>
          </div>
        )}

        {/* Header UI */}
        <div style={{ position: "absolute", top: 20, left: "30%", zIndex: 10, display: "flex", flexDirection: "column", alignItems: "center", color: "#1e293b", fontFamily: "system-ui, sans-serif", pointerEvents: "none", opacity: Math.max(0, 1 - scrollProgress * 3.5), transition: "opacity 0.2s linear" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
            <h1 style={{ fontSize: "5rem", fontWeight: 700, margin: 0, letterSpacing: "2px" }}>
              PyroGuard AI
            </h1>
          </div>
          <p style={{ fontSize: "0.85rem", color: "#64748b", margin: "6px 0 0 0" }}>
            Differentiating Routine Thermal Signals from Industrial Hazards in Real-Time
          </p>
        </div>

        {/* Scroll Down Hint */}
        <div style={{ position: "absolute", bottom: 35, left: "50%", transform: "translateX(-50%)", zIndex: 10, display: "flex", flexDirection: "column", alignItems: "center", gap: "6px", color: "#64748b", fontFamily: "system-ui, sans-serif", fontSize: "12px", opacity: Math.max(0, 1 - scrollProgress * 3.5), transition: "opacity 0.2s linear", pointerEvents: "none" }}>
          <span>Scroll to explore</span>
          <ChevronDown size={18} style={{ animation: "bounce 1.5s infinite" }} />
        </div>
      </div>
    </>
  );
}