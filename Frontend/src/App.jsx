import React from "react";
import ScrollUnwrappingGlobe from "./ScrollUnwrappingGlobe";
import "./App.css";

export default function App() {
  return (
    <main style={{ width: "100vw", height: "100vh", overflow: "hidden" }}>
      <ScrollUnwrappingGlobe />
    </main>
  );
}