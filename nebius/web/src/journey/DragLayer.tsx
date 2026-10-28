/** Inside the 3D canvas: turns screen points into venue coordinates for drag and drop, keeps the
 * camera still while something is dragged, and previews where the dragged thing will land. */
import { Line } from "@react-three/drei";
import { useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import * as THREE from "three";
import type { Pt, Venue } from "@/api/types";
import { centroid, floorY, pointInPolygon, shapeOf } from "@/scene/geom";
import type { ScenePalette } from "@/scene/palette";
import { useEditorDefaults } from "@/lib/useEditorDefaults";
import { type Hit, itemShape, moveObject, type PaletteItem } from "./dragDrop";
import { useDrag } from "./dragStore";

const UP = new THREE.Vector3(0, 1, 0);

export function DragBridge({ venue, exploded }: { venue: Venue; exploded: boolean }) {
  const camera = useThree((s) => s.camera);
  const gl = useThree((s) => s.gl);
  const controls = useThree((s) => s.controls) as unknown as { enabled: boolean } | null;
  useEffect(() => {
    const ray = new THREE.Raycaster();
    const point = new THREE.Vector3();
    const floors = [...venue.floors].sort((a, b) => (b.elevation_m ?? 0) - (a.elevation_m ?? 0));
    useDrag.getState().set({
      pick: (clientX, clientY, floorId) => {
        const r = gl.domElement.getBoundingClientRect();
        if (clientX < r.left || clientX > r.right || clientY < r.top || clientY > r.bottom) return null;
        ray.setFromCamera(new THREE.Vector2(((clientX - r.left) / r.width) * 2 - 1, -((clientY - r.top) / r.height) * 2 + 1), camera);
        let fallback: Hit | null = null;
        for (const f of floorId ? floors.filter((x) => x.floor_id === floorId) : floors) {
          const plane = new THREE.Plane(UP, -floorY(venue, f.floor_id, exploded));
          if (!ray.ray.intersectPlane(plane, point)) continue;
          const hit: Hit = { floorId: f.floor_id, x: +point.x.toFixed(2), y: +(-point.z).toFixed(2), inside: false };
          hit.inside = pointInPolygon(hit.x, hit.y, f.walkable as Pt[]);
          if (hit.inside || floorId) return hit;
          fallback = hit;
        }
        return fallback;
      },
    });
    return () => useDrag.getState().set({ pick: null });
  }, [venue, exploded, camera, gl]);
  useEffect(() => {
    useDrag.getState().set({ controls });
    return () => useDrag.getState().set({ controls: null });
  }, [controls]);
  return null;
}

function Slab({ points, y, color, height, opacity }: { points: Pt[]; y: number; color: string; height: number; opacity: number }) {
  const geo = useMemo(() => {
    const g = new THREE.ExtrudeGeometry(shapeOf(points), { depth: height, bevelEnabled: false });
    g.rotateX(-Math.PI / 2);
    return g;
  }, [points, height]);
  return (
    <group>
      <mesh geometry={geo} position={[0, y, 0]}>
        <meshBasicMaterial color={color} transparent opacity={opacity} depthWrite={false} />
      </mesh>
      <Line points={[...points, points[0]].map((p) => new THREE.Vector3(p[0], y + 0.05, -p[1]))} color={color} lineWidth={3} />
    </group>
  );
}

const ITEM_HEIGHT: Record<PaletteItem, number> = { door: 2.2, fence: 1.1, crowd: 0.15, stall: 2.4 };

function itemColor(item: PaletteItem, palette: ScenePalette): string {
  return item === "door" ? palette.egress : item === "fence" ? palette.caution : item === "crowd" ? palette.zone : palette.booth;
}

/** Translucent preview of the palette item or the grabbed object at the pointer. */
export function DragGhost({ venue, exploded, palette }: { venue: Venue; exploded: boolean; palette: ScenePalette }) {
  const item = useDrag((s) => s.item ?? s.armed);
  const grab = useDrag((s) => s.grab);
  const hit = useDrag((s) => s.hit);
  const ed = useEditorDefaults();
  if (!hit) return null;
  const y = floorY(venue, hit.floorId, exploded) + 0.03;
  if (item) {
    const floor = venue.floors.find((f) => f.floor_id === hit.floorId);
    const shape = floor ? itemShape(floor, item, hit.x, hit.y, ed) : null;
    if (!shape) return null;
    const color = itemColor(item, palette);
    if (item === "fence") {
      return <Line points={shape.points.map((p) => new THREE.Vector3(p[0], y + 0.6, -p[1]))} color={color} lineWidth={8} />;
    }
    return <Slab points={shape.points} y={y} color={color} height={ITEM_HEIGHT[item]} opacity={0.35} />;
  }
  if (grab?.active) {
    const move = moveObject(venue, grab.kind, grab.id, grab.start, [hit.x, hit.y]);
    if (!move || "error" in move) return null;
    let poly: Pt[] | null = move.preview;
    let height = 0.2;
    if (!poly) {
      for (const f of venue.floors) {
        const o = [...f.obstacles, ...f.zones].find((x) => x.id === grab.id);
        if (o) {
          poly = (o.polygon as Pt[]).map(([px, py]) => [px + move.dx, py + move.dy] as Pt);
          height = "kind" in o ? Math.min(o.height_m ?? 1.4, 2.4) : 0.2;
        }
      }
    }
    if (!poly) return null;
    const [cx, cy] = centroid(poly);
    return (
      <group>
        <Slab points={poly} y={y} color={palette.signal} height={grab.kind === "exit" ? 2.2 : height} opacity={0.3} />
        <mesh position={[cx, y + 0.02, -cy]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.35, 0.5, 24]} />
          <meshBasicMaterial color={palette.signal} />
        </mesh>
      </group>
    );
  }
  return null;
}
