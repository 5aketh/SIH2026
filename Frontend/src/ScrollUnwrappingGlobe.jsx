import React, { useRef, useState, useEffect } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Html } from "@react-three/drei";
import { ChevronDown, MapPin, X } from "lucide-react";

import GlobeShadow from "./components/GlobeShadow";
import SatelliteShadow from "./components/SatelliteShadow";
import MorphingGlobeMesh from "./components/MorphingGlobeMesh";
import Satellite from "./components/Satellite";
import GeographicMarker from "./components/GeographicMarker";
import { fetchColorPoints } from "./api";

export default function ScrollUnwrappingGlobe() {
  const [scrollProgress, setScrollProgress] = useState(0);
  const [selectedCity, setSelectedCity] = useState(null);
  const [markersReady, setMarkersReady] = useState(false);
  const [pointsData, setPointsData] = useState([]);
  const [hasFetchedBackend, setHasFetchedBackend] = useState(false);
  const containerRef = useRef();

  // Trigger Backend 0.2s after 2D map complete unrolling
  useEffect(() => {
    let fetchTimer = null;

    if (scrollProgress >= 0.99 && !hasFetchedBackend) {
      fetchTimer = setTimeout(() => {
        fetchColorPoints()
          .then((data) => {
            setPointsData(data);
            setHasFetchedBackend(true);
            setMarkersReady(true);
          })
          .catch((error) => {
            console.error("Failed to fetch points from backend:", error);
            alert("Backend Warning: Failed to fetch geographic points or backend is not responding.");
            setPointsData([]);
            setHasFetchedBackend(true);
          });
      }, 200); // 0.2s delay after full 2D map render
    } else if (scrollProgress < 0.95) {
      setMarkersReady(false);
    }

    return () => {
      if (fetchTimer) clearTimeout(fetchTimer);
    };
  }, [scrollProgress, hasFetchedBackend]);

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
        @import url('https://fonts.googleapis.com/css2?family=Oldenburg&display=swap');

        html, body {
          margin: 0;
          padding: 0;
          width: 100vw;
          height: 100vh;
          overflow: hidden;
          background-color: #ffffff;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }
        * {
          box-sizing: border-box;
        }

        .title-wrapper {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          width: 100%;
          overflow: visible;
        }

        .title-container {
          display: flex;
          align-items: center;
          justify-content: center;
          margin: 0;
          line-height: 1.2;
          white-space: nowrap;
          overflow: visible;
        }

        .font-squada {
          font-family: 'Oldenburg', cursive, serif;
          font-size: clamp(3.5rem, 8.5vw, 7.5rem);
          font-weight: 400;
          letter-spacing: 0px;
          text-transform: none;
          display: inline-block;
          padding-bottom: 0.25em;
          overflow: visible;
        }

        .title-bg-animated-gradient {
          background: linear-gradient(180deg, #dc2626 0%, #ea580c 35%, #f59e0b 70%, #facc15 100%);
          background-size: 100% 250%;
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          animation: verticalFlame 3.5s ease-in-out infinite alternate;
        }

        @keyframes verticalFlame {
          0% {
            background-position: 0% 0%;
          }
          100% {
            background-position: 0% 100%;
          }
        }

        .title-fg-outline {
          color: transparent !important;
          -webkit-text-fill-color: transparent !important;
          -webkit-text-stroke: 1.5px #ffffff;
          filter: drop-shadow(0 2px 10px rgba(0, 0, 0, 0.4));
        }

        @keyframes bounce {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(5px); }
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
        <div
          className="title-wrapper"
          style={{
            position: "absolute",
            top: "16%",
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 0,
            pointerEvents: "none",
            opacity: Math.max(0, 1 - scrollProgress * 3.5),
            transition: "opacity 0.2s linear",
          }}
        >
          <div
            style={{
              fontSize: "0.85rem",
              fontWeight: 700,
              letterSpacing: "4px",
              textTransform: "uppercase",
              color: "transparent",
              marginBottom: "12px",
            }}
          >
            Thermal Intelligence Platform
          </div>

          <h1 className="title-container">
            <span className="font-squada title-bg-animated-gradient">Agnikavach</span>
          </h1>
        </div>

        <div style={{ position: "absolute", top: 0, left: 0, width: "100vw", height: "100vh", zIndex: 1 }}>
          <Canvas camera={{ position: [0, 0, 15], fov: 50, near: 0.1, far: 1000 }} style={{ width: "100%", height: "100%" }}>
            <ambientLight intensity={1.2} />
            <directionalLight position={[0, 0, 12]} intensity={1.5} />

            <GlobeShadow progress={scrollProgress} />
            <SatelliteShadow progress={scrollProgress} />

            <React.Suspense fallback={
              <Html center style={{ color: '#0284c7', fontFamily: 'sans-serif', fontWeight: 600 }}>
                Loading Map...
              </Html>
            }>
              <MorphingGlobeMesh targetProgress={scrollProgress} />
              <Satellite progress={scrollProgress} />
              {pointsData && pointsData.map((group, groupIdx) =>
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
            <OrbitControls enablePan={true} enableZoom={false} minDistance={4.5} maxDistance={25} />
          </Canvas>
        </div>

        <div
          className="title-wrapper"
          style={{
            position: "absolute",
            top: "16%",
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 10,
            pointerEvents: "none",
            opacity: Math.max(0, 1 - scrollProgress * 3.5),
            transition: "opacity 0.2s linear",
          }}
        >
          <div
            style={{
              fontSize: "0.85rem",
              fontWeight: 700,
              letterSpacing: "4px",
              textTransform: "uppercase",
              color: "#0284c7",
              marginBottom: "12px",
            }}
          >
            Thermal Intelligence Platform
          </div>

          <h1 className="title-container">
            <span className="font-squada title-fg-outline">Agnikavach</span>
          </h1>
        </div>

        <div
          style={{
            position: "absolute",
            bottom: 35,
            left: "50%",
            transform: "translateX(-50%)",
            zIndex: 10,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: "6px",
            color: "#64748b",
            fontSize: "12px",
            fontWeight: 500,
            opacity: Math.max(0, 1 - scrollProgress * 3.5),
            transition: "opacity 0.2s linear",
            pointerEvents: "none",
          }}
        >
          <span>Scroll to explore</span>
          <ChevronDown size={16} style={{ animation: "bounce 1.5s infinite" }} />
        </div>

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
      </div>
    </>
  );
}