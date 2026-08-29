#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif

uniform sampler2D uDayMap;
uniform vec3 uSunDirection;
uniform float uProgress;

varying vec2 vUv;
varying vec3 vNormal;

void main() {
  vec4 texColor = texture2D(uDayMap, vUv);
  
  float luminance = dot(texColor.rgb, vec3(0.299, 0.587, 0.114));
  vec3 enhancedColor = texColor.rgb;
  
  if (luminance < 0.22) {
    enhancedColor = mix(vec3(0.15, 0.32, 0.52), texColor.rgb * 1.35, 0.6);
  } else {
    enhancedColor = texColor.rgb * 1.45; 
  }

  // Ensure double-sided lighting illumination on flat map
  vec3 norm = normalize(vNormal);
  if (!gl_FrontFacing) {
    norm = -norm;
  }

  float diff = max(dot(norm, normalize(uSunDirection)), 0.75);
  vec3 baseColor = enhancedColor * (diff + 0.25);
  
  float gridX = step(0.994, fract(vUv.x * 24.0)) + step(0.994, fract(vUv.y * 12.0));
  vec3 gridColor = vec3(0.4, 0.8, 1.0) * gridX * 0.12 * smoothstep(0.6, 1.0, uProgress);

  gl_FragColor = vec4(baseColor + gridColor, 1.0);
}