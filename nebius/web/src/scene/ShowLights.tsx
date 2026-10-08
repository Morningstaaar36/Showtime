/** "Showtime lights": the event night. Sweeping coloured spotlights from each stage onto the
 *  crowd, a glowing LED wall behind the stage and a moonlit sky. Purely visual. */
import { SpotLight } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";
import type { Pt, Venue } from "@/api/types";
import { bbox, centroid, floorY } from "./geom";

const COLORS = ["#ff2e88", "#2ee6ff", "#ffc23d", "#8a5cff", "#3dff9e", "#ff6a2e"];

interface Rig {
  key: string;
  origin: THREE.Vector3;
  aim: THREE.Vector3;
  side: THREE.Vector3; // sweep direction
  color: string;
  phase: number;
}

function stageRigs(venue: Venue, exploded: boolean): { rigs: Rig[]; walls: { pos: THREE.Vector3; rotY: number; w: number; h: number }[] } {
  const rigs: Rig[] = [];
  const walls: { pos: THREE.Vector3; rotY: number; w: number; h: number }[] = [];
  for (const f of venue.floors) {
    const y = floorY(venue, f.floor_id, exploded);
    const crowd = f.zones.length ? centroid(f.zones.flatMap((z) => z.polygon as Pt[])) : centroid(f.walkable as Pt[]);
    for (const o of f.obstacles) {
      if (o.kind !== "stage") continue;
      const poly = o.polygon as Pt[];
      const [sx, sy] = centroid(poly);
      const [x0, y0, x1, y1] = bbox(poly);
      const width = Math.max(x1 - x0, y1 - y0);
      const height = venue.stage?.roof_height_m ?? (venue.mode === "outdoor" ? 10 : 6);
      const toCrowd = new THREE.Vector2(crowd[0] - sx, crowd[1] - sy);
      const dist = Math.max(10, toCrowd.length());
      toCrowd.normalize();
      const side = new THREE.Vector2(-toCrowd.y, toCrowd.x);
      const n = width >= 14 ? 4 : 2;
      for (let i = 0; i < n; i++) {
        const k = i / (n - 1) - 0.5;
        const ox = sx + side.x * k * width * 0.9 + toCrowd.x * 1.5;
        const oy = sy + side.y * k * width * 0.9 + toCrowd.y * 1.5;
        const ax = sx + toCrowd.x * dist * 0.75 + side.x * k * width;
        const ay = sy + toCrowd.y * dist * 0.75 + side.y * k * width;
        rigs.push({
          key: `${o.id}-${i}`,
          origin: new THREE.Vector3(ox, y + height, -oy),
          aim: new THREE.Vector3(ax, y, -ay),
          side: new THREE.Vector3(side.x, 0, -side.y).multiplyScalar(Math.min(dist * 0.35, 30)),
          color: COLORS[(rigs.length) % COLORS.length],
          phase: i * 1.3,
        });
      }
      // LED wall: on the back edge of the stage, facing the crowd
      const back = new THREE.Vector3(sx - toCrowd.x * 0.45 * Math.min(x1 - x0, y1 - y0), y + Math.min(height, 8) * 0.55, -(sy - toCrowd.y * 0.45 * Math.min(x1 - x0, y1 - y0)));
      walls.push({ pos: back, rotY: Math.atan2(toCrowd.x, -toCrowd.y), w: width * 0.85, h: Math.min(height, 8) * 0.6 });
    }
  }
  return { rigs, walls };
}

function Beam({ rig, reduced }: { rig: Rig; reduced: boolean }) {
  const target = useMemo(() => new THREE.Object3D(), []);
  const light = useRef<THREE.SpotLight>(null);
  useFrame(({ clock }) => {
    const t = reduced ? rig.phase : clock.elapsedTime * 0.55 + rig.phase;
    target.position.copy(rig.aim).addScaledVector(rig.side, Math.sin(t));
    target.position.z += Math.cos(t * 0.7) * 3;
    target.updateMatrixWorld();
    if (light.current) light.current.target = target;
  });
  return (
    <>
      <primitive object={target} />
      <SpotLight ref={light} position={rig.origin} color={rig.color} intensity={900} decay={1.2} distance={rig.origin.distanceTo(rig.aim) * 1.8}
                 angle={0.3} penumbra={0.5} attenuation={rig.origin.distanceTo(rig.aim) * 1.6} anglePower={3} opacity={0.75}
                 radiusTop={0.25} radiusBottom={rig.origin.distanceTo(rig.aim) * 0.32} volumetric />
    </>
  );
}

function LedWall({ pos, rotY, w, h, reduced }: { pos: THREE.Vector3; rotY: number; w: number; h: number; reduced: boolean }) {
  const mat = useRef<THREE.MeshStandardMaterial>(null);
  const color = useMemo(() => new THREE.Color(), []);
  useFrame(({ clock }) => {
    if (!mat.current) return;
    const t = reduced ? 0 : clock.elapsedTime * 0.12;
    color.setHSL((t % 1 + 1) % 1, 0.9, 0.55);
    mat.current.emissive.copy(color);
  });
  return (
    <mesh position={pos} rotation={[0, rotY, 0]}>
      <planeGeometry args={[w, h]} />
      <meshStandardMaterial ref={mat} color="#111" emissive="#ff2e88" emissiveIntensity={2.2} side={THREE.DoubleSide} toneMapped={false} />
    </mesh>
  );
}

/** Event-night lighting for every stage in the venue. */
export function ShowLights({ venue, exploded }: { venue: Venue; exploded: boolean }) {
  const { rigs, walls } = useMemo(() => stageRigs(venue, exploded), [venue, exploded]);
  const reduced = typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  return (
    <group>
      {rigs.map((r) => <Beam key={r.key} rig={r} reduced={reduced} />)}
      {walls.map((w, i) => <LedWall key={i} {...w} reduced={reduced} />)}
    </group>
  );
}
