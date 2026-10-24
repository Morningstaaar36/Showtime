/** Replay layers: people (instanced), density heatmap, danger terrain, hotspots, marshals. */
import { useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { Hotspot, Venue } from "@/api/types";
import { fmtClock, fmtNum } from "@/lib/format";
import type { DensityGrid } from "@/replay/density";
import { type AgentKinds, kindsPresent, PEOPLE_KINDS, type PeopleKindId } from "@/replay/kinds";
import type { Trajectory } from "@/replay/trajectory";
import { usePlayback } from "@/state/playback";
import { textHumanizer } from "@/lib/venueText";
import { CIVIDIS } from "./colormaps";
import { floorY } from "./geom";
import type { ScenePalette } from "./palette";
import { PEOPLE_LOOK } from "./peopleLook";
import { SceneHtml } from "./SceneHtml";

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

export function Agents({ traj, density, venue, exploded, palette, onlyFloor = null, ghostOthers = false, kinds = null }: {
  traj: Trajectory; density: DensityGrid | null; venue: Venue; exploded: boolean; palette: ScenePalette;
  /** draw only the people on this floor (one-floor view) */
  onlyFloor?: string | null;
  /** with `onlyFloor`: keep the people on the other floors as faint markers instead of hiding them */
  ghostOthers?: boolean;
  /** who each person is: shape and colour per kind; null = everyone as a general adult */
  kinds?: AgentKinds | null;
}) {
  const max = Math.min(Math.max(traj.index.max_agents, 1), 9000);
  // one instanced mesh per kind present (general adults only: a single mesh, as before)
  const shown = useMemo<PeopleKindId[]>(() => (kinds ? kindsPresent(kinds) : ["general"]), [kinds]);
  const meshes = useRef<(THREE.InstancedMesh | null)[]>([]);
  const buf = useMemo(() => new Float32Array(max * 3), [max]);
  const ids = useMemo(() => new Uint16Array(max), [max]);
  const written = useMemo(() => new Int32Array(PEOPLE_KINDS.length), []);
  const slotOf = useMemo(() => {
    // kind code -> index in `shown` (or 0, the general mesh)
    const a = new Int8Array(PEOPLE_KINDS.length);
    PEOPLE_KINDS.forEach((k, i) => { a[i] = Math.max(0, shown.indexOf(k)); });
    return a;
  }, [shown]);
  const ys = useFloorYs(venue, traj.index.floors, exploded);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const bases = useMemo(() => shown.map((k) => new THREE.Color(PEOPLE_LOOK[k].color ?? palette.agent)), [shown, palette.agent]);
  const geometries = useMemo(() => shown.map((k) => PEOPLE_LOOK[k].geometry()), [shown]);
  useEffect(() => () => geometries.forEach((g) => g.dispose()), [geometries]);
  const tmp = useMemo(() => new THREE.Color(), []);
  const faint = useMemo(() => new THREE.Color(palette.bg), [palette.bg]);
  const heatMax = density?.displayMax ?? DENSITY_MAX;
  const only = onlyFloor ? traj.index.floors.indexOf(onlyFloor) : -1;
  const densFloor = useMemo(() => {
    // traj floor index -> density floor index
    const dIdx = density?.index.floors ?? [];
    return traj.index.floors.map((f) => dIdx.indexOf(f));
  }, [traj, density]);

  useEffect(() => {
    meshes.current.forEach((m, s) => {
      if (!m) return;
      for (let i = 0; i < max; i++) m.setColorAt(i, bases[s]);
      if (m.instanceColor) m.instanceColor.needsUpdate = true;
    });
  }, [max, bases]);

  useFrame(() => {
    const ms = meshes.current;
    if (!ms[0]) return;
    const t = usePlayback.getState().t;
    const n = traj.sample(t, buf, kinds ? ids : undefined);
    const frame = density ? density.pairAt(t)[0] : -1;
    written.fill(0); // instances written per mesh (people on hidden floors are skipped)
    for (let j = 0; j < n; j++) {
      const x = buf[j * 3];
      const y = buf[j * 3 + 1];
      const f = buf[j * 3 + 2] | 0;
      const other = only >= 0 && f !== only;
      if (other && !ghostOthers) continue;
      const s = kinds ? slotOf[kinds.lookup[ids[j]]] : 0;
      const m = ms[s];
      if (!m) continue;
      const i = written[s]++;
      dummy.position.set(x, (ys[f] ?? 0) + 0.02, -y);
      dummy.updateMatrix();
      m.setMatrixAt(i, dummy.matrix);
      if (only >= 0) {
        // slots move between frames once some people are faint: every marker gets its colour
        if (other) tmp.copy(bases[s]).lerp(faint, 0.62);
        else tmp.copy(bases[s]);
        if (!other && density && frame >= 0 && densFloor[f] >= 0) {
          const d = density.at(frame, densFloor[f], x, y);
          tmp.lerp(LUT_COLORS[Math.min(255, Math.round((d / heatMax) * 255))], Math.min(1, Math.max(0, (d - 1.0) / 2.5)));
        }
        m.setColorAt(i, tmp);
      } else if (density && frame >= 0 && densFloor[f] >= 0) {
        const d = density.at(frame, densFloor[f], x, y);
        const k = Math.min(1, Math.max(0, (d - 1.0) / 2.5));
        const lut = LUT_COLORS[Math.min(255, Math.round((d / heatMax) * 255))];
        // with people kinds the shape carries the kind, so a crush still tints every marker
        tmp.copy(bases[s]).lerp(lut, k);
        m.setColorAt(i, tmp);
      }
    }
    ms.forEach((m, s) => {
      if (!m) return;
      m.count = written[s];
      m.instanceMatrix.needsUpdate = true;
      if (m.instanceColor) m.instanceColor.needsUpdate = true;
    });
  });

  return (
    <group>
      {shown.map((k, s) => (
        <instancedMesh key={k} ref={(m) => { meshes.current[s] = m; }} args={[geometries[s], undefined, max]} frustumCulled={false}>
          <meshStandardMaterial roughness={0.55} metalness={0.05} />
        </instancedMesh>
      ))}
    </group>
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
  uniform float uFadeLo;
  uniform float uFadeHi;
  uniform float uSolid;
  uniform vec3 uDangerColor;
  uniform vec3 uWarnColor;
  void main() {
    float d = mix(texture2D(uA, vUv).r, texture2D(uB, vUv).r, uMix) * 255.0 * uScale;
    vec3 col = texture2D(uLut, vec2(clamp(d / uMaxD, 0.0, 1.0), 0.5)).rgb;
    // heat fades in over the layer's own range (people per m² or, for turbulence, 1/s²)
    float alpha = mix(smoothstep(uFadeLo, uFadeHi, d) * uOpacity, step(uFadeLo * 0.35, d) * 0.92, uSolid);
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
export function DensityLayer({ density, venue, exploded, palette, terrain, onlyFloor = null }: {
  density: DensityGrid; venue: Venue; exploded: boolean; palette: ScenePalette; terrain: boolean;
  /** draw only this floor's heatmap (one-floor view) */
  onlyFloor?: string | null;
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
      uMaxD: { value: density.displayMax ?? DENSITY_MAX }, uOpacity: { value: 0.8 }, uLift: { value: 0 }, uSolid: { value: 0 },
      // a density grid fades in from about a third of a person per m²; another layer (crowd
      // pressure) from half its warning level up to its danger level
      uFadeLo: { value: density.displayMax == null ? 0.35 : warn * 0.5 },
      uFadeHi: { value: density.displayMax == null ? 1.6 : Math.max(danger, warn * 1.01) },
      uDangerColor: { value: new THREE.Color(palette.danger) },
      uWarnColor: { value: new THREE.Color(palette.caution) },
    },
  })), [layers, lut, scale, danger, warn, palette.danger, palette.caution, density.displayMax]);

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
        if (onlyFloor && fid !== onlyFloor) return null;
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
              <SceneHtml position={[0, 2.6, 0]} center zIndexRange={[40, 0]}
                    style={{ display: visible && (labelled.has(key) || selectedKey === key) ? "block" : "none" }}>
                <button
                  type="button"
                  onClick={() => onSelect(h, key)}
                  className={`whitespace-nowrap rounded-[4px] px-1.5 py-0.5 text-2xs font-semibold text-on-strong shadow tabular ${h.level === "danger" ? "bg-danger-strong" : "bg-caution-strong"}`}
                >
                  {fmtNum(h.peak_density_ppm2, 1)} people per m² · {fmtClock(h.t_s)}
                </button>
              </SceneHtml>
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
        <SceneHtml key={i} position={[m.x, floorY(venue, m.floor_id, exploded) + 3.2, -m.y]} center zIndexRange={[50, 0]}
              style={{ display: t >= m.t_s && t <= m.t_s + 10 ? "block" : "none" }}>
          <div className="relative max-w-56 rounded-[8px] border border-border bg-surface px-2.5 py-1.5 text-xs text-ink shadow-[var(--shadow-float)]">
            <span className="mr-1 font-semibold text-signal">Marshal:</span>{human(m.speech)}
            <span className="absolute -bottom-1.5 left-1/2 size-3 -translate-x-1/2 rotate-45 border-b border-r border-border bg-surface" />
          </div>
        </SceneHtml>
      ))}
    </group>
  );
}
