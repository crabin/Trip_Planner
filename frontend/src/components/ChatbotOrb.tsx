import { Canvas, useFrame } from "@react-three/fiber";
import React, { useMemo, useRef } from "react";
import * as THREE from "three";

export type ChatbotOrbState = null | "thinking" | "listening" | "talking";

interface ChatbotOrbProps {
  state: ChatbotOrbState;
}

const ORB_CONFIG: Record<NonNullable<ChatbotOrbState> | "idle", {
  colorA: string;
  colorB: string;
  colorC: string;
  amplitude: number;
  pulse: number;
  speed: number;
}> = {
  idle: {
    colorA: "#153f3b",
    colorB: "#d7ad58",
    colorC: "#f4ead3",
    amplitude: 0.08,
    pulse: 0.04,
    speed: 0.36,
  },
  listening: {
    colorA: "#1f574f",
    colorB: "#7dcfb6",
    colorC: "#f7efd9",
    amplitude: 0.12,
    pulse: 0.08,
    speed: 0.58,
  },
  thinking: {
    colorA: "#143c38",
    colorB: "#d7ad58",
    colorC: "#fff6d8",
    amplitude: 0.19,
    pulse: 0.12,
    speed: 0.92,
  },
  talking: {
    colorA: "#174944",
    colorB: "#e5b95c",
    colorC: "#ffffff",
    amplitude: 0.28,
    pulse: 0.18,
    speed: 1.24,
  },
};

function ChatbotOrbMesh({ state }: ChatbotOrbProps) {
  const meshRef = useRef<THREE.Mesh<THREE.IcosahedronGeometry, THREE.ShaderMaterial> | null>(null);
  const config = ORB_CONFIG[state ?? "idle"];
  const uniforms = useMemo(
    () => ({
      uTime: { value: 0 },
      uColorA: { value: new THREE.Color(config.colorA) },
      uColorB: { value: new THREE.Color(config.colorB) },
      uColorC: { value: new THREE.Color(config.colorC) },
      uAmplitude: { value: config.amplitude },
      uPulse: { value: config.pulse },
      uSpeed: { value: config.speed },
    }),
    [],
  );

  useFrame(({ clock }) => {
    const mesh = meshRef.current;
    const material = mesh?.material;
    if (!mesh || !material) {
      return;
    }

    material.uniforms.uTime.value = clock.getElapsedTime();
    material.uniforms.uColorA.value.lerp(new THREE.Color(config.colorA), 0.06);
    material.uniforms.uColorB.value.lerp(new THREE.Color(config.colorB), 0.06);
    material.uniforms.uColorC.value.lerp(new THREE.Color(config.colorC), 0.06);
    material.uniforms.uAmplitude.value = THREE.MathUtils.lerp(material.uniforms.uAmplitude.value, config.amplitude, 0.08);
    material.uniforms.uPulse.value = THREE.MathUtils.lerp(material.uniforms.uPulse.value, config.pulse, 0.08);
    material.uniforms.uSpeed.value = THREE.MathUtils.lerp(material.uniforms.uSpeed.value, config.speed, 0.08);

    mesh.rotation.x = Math.sin(clock.elapsedTime * 0.24) * 0.12;
    mesh.rotation.y += 0.004 + material.uniforms.uSpeed.value * 0.0015;
  });

  return React.createElement(
    "mesh",
    { ref: meshRef },
    React.createElement("icosahedronGeometry", { args: [1.22, 64] }),
    React.createElement("shaderMaterial", {
      transparent: true,
      depthWrite: false,
      uniforms,
      vertexShader: `
        varying vec2 vUv;
        varying vec3 vNormal;
        uniform float uTime;
        uniform float uAmplitude;
        uniform float uPulse;
        uniform float uSpeed;

        float wave(vec3 position, float offset) {
          return sin(position.x * 4.8 + uTime * uSpeed + offset)
            + sin(position.y * 5.6 + uTime * uSpeed * 1.18 + offset)
            + sin(position.z * 6.4 + uTime * uSpeed * 0.82 + offset);
        }

        void main() {
          vUv = uv;
          vNormal = normalize(normalMatrix * normal);
          float distortion = wave(position, 0.0) * uAmplitude;
          float breath = sin(uTime * uSpeed * 2.4) * uPulse;
          vec3 newPosition = position + normal * (distortion + breath);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(newPosition, 1.0);
        }
      `,
      fragmentShader: `
        varying vec2 vUv;
        varying vec3 vNormal;
        uniform float uTime;
        uniform float uSpeed;
        uniform vec3 uColorA;
        uniform vec3 uColorB;
        uniform vec3 uColorC;

        void main() {
          float fresnel = pow(1.0 - abs(vNormal.z), 2.0);
          float sweep = 0.5 + 0.5 * sin((vUv.x * 7.0) + (vUv.y * 5.0) + uTime * uSpeed * 1.7);
          vec3 color = mix(uColorA, uColorB, smoothstep(0.12, 0.92, sweep));
          color = mix(color, uColorC, fresnel * 0.72);
          float alpha = 0.82 + fresnel * 0.18;
          gl_FragColor = vec4(color, alpha);
        }
      `,
    }),
  );
}

export function ChatbotOrb({ state }: ChatbotOrbProps) {
  return React.createElement(
    "span",
    {
      className: `floating-chatbot__orb floating-chatbot__orb--${state ?? "idle"}`,
      "aria-hidden": true,
    },
    React.createElement(
      Canvas,
      {
        camera: { position: [0, 0, 3.1], fov: 42 },
        dpr: [1, 1.6],
        gl: {
          alpha: true,
          antialias: true,
          powerPreference: "low-power",
        },
      },
      React.createElement("ambientLight", { intensity: 1.8 }),
      React.createElement("directionalLight", { position: [2.6, 3.2, 4], intensity: 1.9 }),
      React.createElement("pointLight", { position: [-2, -1.6, 2.4], intensity: 1.2, color: "#d7ad58" }),
      React.createElement(ChatbotOrbMesh, { state }),
    ),
    React.createElement("span", { className: "floating-chatbot__orb-fallback" }),
  );
}
