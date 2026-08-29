precision highp float;

uniform float uProgress;
varying vec2 vUv;
varying vec3 vNormal;

#define PI 3.1415926535897932384626433832795

void main() {
  vUv = uv;
  float R = 3.0;
  
  float lon = (uv.x - 0.5) * 2.0 * PI;
  float lat = (uv.y - 0.5) * PI;

  // Phase 1: Globe -> Cylinder
  float t1 = clamp(uProgress / 0.5, 0.0, 1.0);
  float rLat = R * mix(cos(lat), 1.0, t1);
  vec3 posCylinder = vec3(
    rLat * sin(lon),
    R * mix(sin(lat), lat, t1),
    rLat * cos(lon)
  );

  // Phase 2: Cylinder -> Flat Plane
  float t2 = clamp((uProgress - 0.5) / 0.5, 0.0, 1.0);
  vec3 posUnrolling = vec3(
    R * mix(sin(lon), lon, t2),
    R * lat,
    R * cos(lon) * (1.0 - t2)
  );

  vec3 finalPos = mix(posCylinder, posUnrolling, t2);

  // Compute normals smooth transition
  vec3 nSphere = normalize(vec3(cos(lat) * sin(lon), sin(lat), cos(lat) * cos(lon)));
  vec3 nPlane = vec3(0.0, 0.0, 1.0);
  vNormal = normalize(normalMatrix * mix(nSphere, nPlane, uProgress));

  gl_Position = projectionMatrix * modelViewMatrix * vec4(finalPos, 1.0);
}