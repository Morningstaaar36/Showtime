/** Replay layers: people (instanced), density heatmap, danger terrain, hotspots, marshals. */
import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { Hotspot, Venue } from "@/api/types";
import { fmtClock, fmtNum } from "@/lib/format";
import type { DensityGrid } from "@/replay/density";
import type { Trajectory } from "@/replay/trajectory";
import { usePlayback } from "@/state/playback";
import { textHumanizer } from "@/lib/venueText";
import { CIVIDIS } from "./colormaps";
import { floorY } from "./geom";
import type { ScenePalette } from "./palette";

export const DENSITY_MAX = 7; // colormap range (people per m²)
const TERRAIN_SCALE = 0.55; // metres of height per person per m²

/** Advances the replay clock once per rendered frame. */
export function PlaybackClock() {
  useFrame((_, dt) => usePlayback.getState().tick(Math.min(dt, 0.1)));
  return null;
}

function lutTexture(): THREE.DataTexture {
  const data = new Uint8Array(256 * 4);
  for (let i = 0; i < 256; i++) {
    data[i * 4] = CIVIDIS[i * 3];
    data[i * 4 + 1] = CIVIDIS[i * 3 + 1];
    data[i * 4 + 2] = CIVIDIS[i * 3 + 2];
    data[i * 4 + 3] = 255;
  }
  const tex = new THREE.DataTexture(data, 256, 1, THREE.RGBAFormat);
  tex.magFilter = THREE.LinearFilter;
  tex.minFilter = THREE.LinearFilter;
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.needsUpdate = true;
  return tex;
}

const LUT_COLORS: THREE.Color[] = Array.from({ length: 256 }, (_, i) =>
  new THREE.Color().setRGB(CIVIDIS[i * 3] / 255, CIVIDIS[i * 3 + 1] / 255, CIVIDIS[i * 3 + 2] / 255,
                           THREE.SRGBColorSpace));

/** Map traj floor index -> world Y. */
function useFloorYs(venue: Venue, floors: string[], exploded: boolean): number[] {
  return useMemo(() => floors.map((fid) => floorY(venue, fid, exploded)), [venue, floors, exploded]);
}

export function Agents({ traj, density, venue, exploded, palette }: {
  traj: Trajectory; density: DensityGrid | null; venue: Venue; exploded: boolean; palette: ScenePalette;
}) {
  const max = Math.min(Math.max(traj.index.max_agents, 1), 9000);
  const mesh = useRef<THREE.InstancedMesh>(null);
  const buf = useMemo(() => new Float32Array(max * 3), [max]);
  const ys = useFloorYs(venue, traj.index.floors, exploded);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const base = useMemo(() => new THREE.Color(palette.agent), [palette.agent]);
  const tmp = useMemo(() => new THREE.Color(), []);
  const densFloor = useMemo(() => {
    // traj floor index -> density floor index
    const dIdx = density?.index.floors ?? [];
    return traj.index.floors.map((f) => dIdx.indexOf(f));
  }, [traj, density]);

  useEffect(() => {
    const m = mesh.current;
    if (!m) return;
    for (let i = 0; i < max; i++) m.setColorAt(i, base);
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
  }, [max, base]);

  useFrame(() => {
    const m = mesh.current;
    if (!m) return;
    const t = usePlayback.getState().t;
    const n = traj.sample(t, buf);
    const frame = density ? density.pairAt(t)[0] : -1;
    for (let i = 0; i < n; i++) {
      const x = buf[i * 3];
      const y = buf[i * 3 + 1];
      const f = buf[i * 3 + 2] | 0;
      dummy.position.set(x, (ys[f] ?? 0) + 0.56, -y);
      dummy.updateMatrix();
      m.setMatrixAt(i, dummy.matrix);
      if (density && frame >= 0 && densFloor[f] >= 0) {
        const d = density.at(frame, densFloor[f], x, y);
        const k = Math.min(1, Math.max(0, (d - 1.0) / 2.5));
        const lut = LUT_COLORS[Math.min(255, Math.round((d / DENSITY_MAX) * 255))];
        tmp.copy(base).lerp(lut, k);
        m.setColorAt(i, tmp);
      }
    }
    m.count = n;
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
  });

  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, max]} frustumCulled={false}>
      <capsuleGeometry args={[0.18, 0.72, 2, 10]} />
      <meshStandardMaterial roughness={0.55} metalness={0.05} />
    </instancedMesh>
  );
}

const HEAT_VERT = /* glsl */ `
  varying vec2 vUv;
  uniform sampler2D uA;
  uniform sampler2D uB;
  uniform float uMix;
  uniform float uScale;
  uniform float uLift;
  varying float vD;
  void main() {
    vUv = uv;
    float d = mix(texture2D(uA, uv).r, texture2D(uB, uv).r, uMix) * 255.0 * uScale;
    vD = d;
    vec3 p = position;
    p.z += d * uLift;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(p, 1.0);
  }
`;

const HEAT_FRAG = /* glsl */ `
  varying vec2 vUv;
  varying float vD;
  uniform sampler2D uA;
  uniform sampler2D uB;
  uniform sampler2D uLut;
  uniform float uMix;
  uniform float uScale;
  uniform float uDanger;
  uniform float uWarn;
  uniform float uMaxD;
  uniform float uOpacity;
  uniform float uSolid;
  uniform vec3 uDangerColor;
  uniform vec3 uWarnColor;
  void main() {
    float d = mix(texture2D(uA, vUv).r, texture2D(uB, vUv).r, uMix) * 255.0 * uScale;
    vec3 col = texture2D(uLut, vec2(clamp(d / uMaxD, 0.0, 1.0), 0.5)).rgb;
    float alpha = mix(smoothstep(0.35, 1.6, d) * uOpacity, step(0.12, d) * 0.92, uSolid);
    float w = max(fwidth(d), 1e-4);
    float danger = 1.0 - smoothstep(0.0, w * 1.6, abs(d - uDanger));
    float warn = (1.0 - smoothstep(0.0, w * 1.2, abs(d - uWarn))) * 0.55;
    col = mix(col, uWarnColor, warn);
    col = mix(col, uDangerColor, danger);
    float a = max(alpha, max(danger * 0.95, warn * 0.6));
    if (a < 0.01) discard;
    gl_FragColor = vec4(col, a);
    #include <colorspace_fragment>
  }
`;

/** Density as a coloured overlay on each floor, with warning and danger contours. */
export function DensityLayer({ density, venue, exploded, palette, terrain }: {
  density: DensityGrid; venue: Venue; exploded: boolean; palette: ScenePalette; terrain: boolean;
}) {
  const { nx, ny, cell_m: cell, origin, floors, scale, warn, danger } = density.index;
  const lut = useMemo(lutTexture, []);
  const layers = useMemo(() => floors.map(() => {
    const mk = () => {
      const tex = new THREE.DataTexture(new Uint8Array(nx * ny), nx, ny, THREE.RedFormat, THREE.UnsignedByteType);
      tex.magFilter = THREE.LinearFilter;
      tex.minFilter = THREE.LinearFilter;
      tex.needsUpdate = true;
      return tex;
    };
    return { a: mk(), b: mk(), ka: -1, kb: -1 };
  }), [floors, nx, ny]);
  const materials = useMemo(() => layers.map((L) => new THREE.ShaderMaterial({
    vertexShader: HEAT_VERT,
    fragmentShader: HEAT_FRAG,
    transparent: true,
    depthWrite: false,
    side: THREE.DoubleSide,
    uniforms: {
      uA: { value: L.a }, uB: { value: L.b }, uMix: { value: 0 }, uLut: { value: lut },
      uScale: { value: scale }, uDanger: { value: danger }, uWarn: { value: warn },
      uMaxD: { value: DENSITY_MAX }, uOpacity: { value: 0.8 }, uLift: { value: 0 }, uSolid: { value: 0 },
      uDangerColor: { value: new THREE.Color(palette.danger) },
      uWarnColor: { value: new THREE.Color(palette.caution) },
    },
  })), [layers, lut, scale, danger, warn, palette.danger, palette.caution]);

  useEffect(() => () => {
    for (const L of layers) { L.a.dispose(); L.b.dispose(); }
    for (const m of materials) m.dispose();
  }, [layers, materials]);
  useEffect(() => () => lut.dispose(), [lut]);

  useFrame(() => {
    const t = usePlayback.getState().t;
    const [ka, kb, f] = density.pairAt(t);
    layers.forEach((L, fi) => {
      if (L.ka !== ka) {
        (L.a.image.data as Uint8Array).set(density.slice(ka, fi));
        L.a.needsUpdate = true;
        L.ka = ka;
      }
      if (L.kb !== kb) {
        (L.b.image.data as Uint8Array).set(density.slice(kb, fi));
        L.b.needsUpdate = true;
        L.kb = kb;
      }
      const u = materials[fi].uniforms;
      u.uMix.value = f;
      u.uLift.value = terrain ? TERRAIN_SCALE : 0;
      u.uSolid.value = terrain ? 1 : 0;
    });
  });

  const w = nx * cell;
  const h = ny * cell;
  return (
    <group>
      {floors.map((fid, i) => {
        const y = floorY(venue, fid, exploded) + 0.05;
        return (
          <group key={fid}>
            <mesh position={[origin[0] + w / 2, y, -(origin[1] + h / 2)]} rotation={[-Math.PI / 2, 0, 0]}
                  material={materials[i]} renderOrder={2}>
              <planeGeometry args={[w, h, terrain ? nx - 1 : 1, terrain ? ny - 1 : 1]} />
            </mesh>
            {terrain && (
              <mesh position={[origin[0] + w / 2, y + danger * TERRAIN_SCALE, -(origin[1] + h / 2)]}
                    rotation={[-Math.PI / 2, 0, 0]} renderOrder={3}>
                <planeGeometry args={[w, h]} />
                <meshBasicMaterial color={palette.danger} transparent opacity={0.12} depthWrite={false}
                                   side={THREE.DoubleSide} />
              </mesh>
            )}
          </group>
        );
      })}
    </group>
  );
}

/** Pulsing rings at hotspots; click to select (then "Ask the venue"). */
export function Hotspots({ hotspots, venue, exploded, palette, labels, selectedKey, onSelect, showAll }: {
  hotspots: Hotspot[]; venue: Venue; exploded: boolean; palette: ScenePalette; labels: boolean;
  selectedKey: string | null; onSelect: (h: Hotspot, key: string) => void; showAll: boolean;
}) {
  const group = useRef<THREE.Group>(null);
  const [t, setT] = useState(0);
  useFrame((state) => {
    const time = state.clock.elapsedTime;
    group.current?.children.forEach((c, i) => {
      const ring = c.children[0] as THREE.Mesh | undefined;
      if (!ring) return;
      const s = 1 + ((time * 0.6 + i * 0.37) % 1) * 0.8;
      ring.scale.set(s, s, s);
      (ring.material as THREE.MeshBasicMaterial).opacity = 0.9 * (1 - ((time * 0.6 + i * 0.37) % 1));
    });
    const pt = usePlayback.getState().t;
    if (Math.abs(pt - t) > 0.5) setT(pt);
  });
  const items = useMemo(() => hotspots.slice(0, 8), [hotspots]);
  // One label per cluster: hotspots are sorted worst first; nearby ones keep only their ring.
  const labelled = useMemo(() => {
    const kept: Hotspot[] = [];
    for (const h of items) {
      if (!kept.some((k) => k.floor_id === h.floor_id && Math.hypot(k.x - h.x, k.y - h.y) < 10)) kept.push(h);
    }
    return new Set(kept.map((h) => `${h.floor_id}:${h.x}:${h.y}`));
  }, [items]);
  return (
    <group ref={group}>
      {items.map((h, i) => {
        const key = `${h.floor_id}:${h.x}:${h.y}`;
        const visible = showAll || t >= (h.t_s ?? 0) - 20;
        const color = h.level === "danger" ? palette.danger : palette.caution;
        const y = floorY(venue, h.floor_id, exploded) + 0.12;
        const r = Math.min(3.5, 0.9 + Math.sqrt((h as Hotspot & { cells?: number }).cells ?? 4) * 0.35);
        return (
          <group key={key} position={[h.x, y, -h.y]} visible={visible}>
            <mesh rotation={[-Math.PI / 2, 0, 0]}>
              <ringGeometry args={[r * 0.82, r, 48]} />
              <meshBasicMaterial color={color} transparent opacity={0.8} depthWrite={false} />
            </mesh>
            <mesh rotation={[-Math.PI / 2, 0, 0]} onClick={(e) => { e.stopPropagation(); onSelect(h, key); }}
                  onPointerOver={() => { document.body.style.cursor = "pointer"; }}
                  onPointerOut={() => { document.body.style.cursor = ""; }}>
              <circleGeometry args={[r * 0.8, 32]} />
              <meshBasicMaterial color={color} transparent opacity={selectedKey === key ? 0.35 : 0.14} depthWrite={false} />
            </mesh>
            {labels && (
              <Html position={[0, 2.6, 0]} center zIndexRange={[40, 0]}
                    style={{ display: visible && (labelled.has(key) || selectedKey === key) ? "block" : "none" }}>
                <button
                  type="button"
                  onClick={() => onSelect(h, key)}
                  className={`whitespace-nowrap rounded-[4px] px-1.5 py-0.5 text-2xs font-semibold text-white shadow tabular ${h.level === "danger" ? "bg-danger" : "bg-caution"}`}
                >
                  {fmtNum(h.peak_density_ppm2, 1)} people per m² · {fmtClock(h.t_s)}
                </button>
              </Html>
            )}
            {i === 0 && <pointLight color={color} intensity={selectedKey === key ? 6 : 2} distance={8} position={[0, 1.5, 0]} />}
          </group>
        );
      })}
    </group>
  );
}

export interface MarshalNote {
  t_s: number;
  x: number;
  y: number;
  floor_id: string;
  speech: string;
}

/** Speech bubbles where marshals redirect people (shown for 10 s after each decision). */
export function Marshals({ notes, venue, exploded }: { notes: MarshalNote[]; venue: Venue; exploded: boolean }) {
  const human = useMemo(() => textHumanizer(venue), [venue]);
  const [t, setT] = useState(0);
  useFrame(() => {
    const pt = usePlayback.getState().t;
    if (Math.abs(pt - t) > 0.25) setT(pt);
  });
  return (
    <group>
      {notes.map((m, i) => (
        <Html key={i} position={[m.x, floorY(venue, m.floor_id, exploded) + 3.2, -m.y]} center zIndexRange={[50, 0]}
              style={{ display: t >= m.t_s && t <= m.t_s + 10 ? "block" : "none" }}>
          <div className="relative max-w-56 rounded-[8px] border border-border bg-surface px-2.5 py-1.5 text-xs text-ink shadow-[var(--shadow-float)]">
            <span className="mr-1 font-semibold text-signal">Marshal:</span>{human(m.speech)}
            <span className="absolute -bottom-1.5 left-1/2 size-3 -translate-x-1/2 rotate-45 border-b border-r border-border bg-surface" />
          </div>
        </Html>
      ))}
    </group>
  );
}
