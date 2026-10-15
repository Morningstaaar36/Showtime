/** Plan-mode editing in 3D: drag to move, draw barriers and zones, place exits, measure. */
import { Html, Line, TransformControls } from "@react-three/drei";
import { useMemo, useRef, useState } from "react";
import * as THREE from "three";
import type { Pt, Venue } from "@/api/types";
import { lockedIds } from "@/lib/annotations";
import { fmtNum } from "@/lib/format";
import type { ObjectChange } from "@/lib/venueDiff";
import { useUi } from "@/state/ui";
import { bbox, centroid, exitRectAt, floorY } from "./geom";
import type { ScenePalette } from "./palette";

export interface EditCallbacks {
  onMove: (id: string, dx: number, dy: number) => void;
}

function objectPolygon(venue: Venue, id: string): { poly: Pt[]; floorId: string; height: number } | null {
  for (const f of venue.floors) {
    for (const o of f.obstacles) if (o.id === id) return { poly: o.polygon as Pt[], floorId: f.floor_id, height: o.height_m ?? 1.5 };
    for (const e of f.exits) if (e.id === id) return { poly: e.polygon as Pt[], floorId: f.floor_id, height: 2.3 };
    for (const z of f.zones) if (z.id === id) return { poly: z.polygon as Pt[], floorId: f.floor_id, height: 0.2 };
  }
  return null;
}

/** Translate gizmo on the selected object; snaps to 0.5 m and sends one `move` patch on release. */
export function MoveGizmo({ venue, exploded, palette, onMove }: { venue: Venue; exploded: boolean; palette: ScenePalette } & EditCallbacks) {
  const selection = useUi((s) => s.selection);
  const proxy = useRef<THREE.Mesh>(null);
  const [dragging, setDragging] = useState(false);
  const info = selection ? objectPolygon(venue, selection.id) : null;
  if (!selection || !info || selection.kind === "hotspot" || selection.kind === "stair") return null;
  // a locked object has no handle: the organizer unlocks it first
  if (lockedIds(venue).has(selection.id)) return null;
  const [cx, cy] = centroid(info.poly);
  const [x0, y0, x1, y1] = bbox(info.poly);
  const y = floorY(venue, info.floorId, exploded);
  const h = Math.max(info.height, 0.3);
  return (
    <TransformControls
      key={`${selection.id}:${cx}:${cy}`}
      mode="translate"
      showY={false}
      translationSnap={0.5}
      size={0.8}
      position={[cx, y + h / 2, -cy]}
      onMouseDown={() => setDragging(true)}
      onMouseUp={() => {
        setDragging(false);
        const p = proxy.current?.parent?.position;
        if (!p) return;
        const dx = +(p.x - cx).toFixed(2);
        const dy = +(-p.z - cy).toFixed(2);
        if (Math.abs(dx) > 0.01 || Math.abs(dy) > 0.01) onMove(selection.id, dx, dy);
      }}
    >
      <mesh ref={proxy}>
        <boxGeometry args={[Math.max(x1 - x0, 0.3), h, Math.max(y1 - y0, 0.3)]} />
        <meshBasicMaterial color={palette.signal} transparent opacity={dragging ? 0.28 : 0.08} depthWrite={false} />
      </mesh>
    </TransformControls>
  );
}

/** Preview of what the active drawing tool will create. */
export function DraftPreview({ venue, exploded, palette, cursor }: {
  venue: Venue; exploded: boolean; palette: ScenePalette; cursor: { floorId: string; x: number; y: number } | null;
}) {
  const tool = useUi((s) => s.tool);
  const draft = useUi((s) => s.draft);
  const floorId = cursor?.floorId ?? venue.floors[0].floor_id;
  const y = floorY(venue, floorId, exploded) + 0.06;
  const pts = useMemo(() => {
    const all = cursor ? [...draft, [cursor.x, cursor.y] as [number, number]] : draft;
    return all.map((p) => new THREE.Vector3(p[0], y, -p[1]));
  }, [draft, cursor, y]);

  if (tool === "exit" && cursor) {
    const floor = venue.floors.find((f) => f.floor_id === cursor.floorId);
    const rect = floor ? exitRectAt(floor.walkable as Pt[], cursor.x, cursor.y, 2.0) : null;
    if (!rect) return null;
    const [cx, cy] = centroid(rect);
    return (
      <group>
        <Line points={[...rect, rect[0]].map((p) => new THREE.Vector3(p[0], y + 0.02, -p[1]))} color={palette.egress} lineWidth={3} />
        <mesh position={[cx, y + 1.1, -cy]}>
          <boxGeometry args={[0.3, 2.2, 0.3]} />
          <meshBasicMaterial color={palette.egress} transparent opacity={0.45} />
        </mesh>
      </group>
    );
  }
  if ((tool === "barrier" || tool === "zone" || tool === "measure") && pts.length >= 1) {
    const closed = tool === "zone" && pts.length >= 3 ? [...pts, pts[0]] : pts;
    let length = 0;
    for (let i = 1; i < pts.length; i++) length += pts[i].distanceTo(pts[i - 1]);
    const last = pts[pts.length - 1];
    const color = tool === "barrier" ? palette.ink : tool === "zone" ? palette.zone : palette.signal;
    return (
      <group>
        {closed.length >= 2 && <Line points={closed} color={color} lineWidth={tool === "barrier" ? 4 : 2} dashed={tool !== "barrier"} dashSize={0.6} gapSize={0.35} />}
        {pts.map((p, i) => (
          <mesh key={i} position={p}>
            <sphereGeometry args={[0.18, 12, 12]} />
            <meshBasicMaterial color={color} />
          </mesh>
        ))}
        {tool === "measure" && pts.length >= 2 && (
          <Html position={[last.x, last.y + 0.8, last.z]} center zIndexRange={[30, 0]} style={{ pointerEvents: "none" }}>
            <div className="rounded-[3px] bg-ink px-1.5 py-0.5 text-2xs font-semibold text-plan tabular">{fmtNum(length, 1)} m</div>
          </Html>
        )}
      </group>
    );
  }
  return null;
}

/** Outlines of what a proposal adds, changes or removes, drawn just above the floor. */
export function ChangeHighlights({ venue, changes, exploded, palette }: {
  venue: Venue; changes: ObjectChange[]; exploded: boolean; palette: ScenePalette;
}) {
  return (
    <group>
      {changes.map((c) => {
        const y = floorY(venue, c.floorId, exploded) + 0.08;
        const pts = [...c.polygon, c.polygon[0]].map(([x, z]) => new THREE.Vector3(x, y, -z));
        const color = c.kind === "removed" ? palette.edge : palette.signal;
        return (
          <Line key={`${c.kind}:${c.id}`} points={pts} color={color} lineWidth={c.kind === "added" ? 4 : 3}
                dashed={c.kind !== "added"} dashSize={0.5} gapSize={0.3} />
        );
      })}
    </group>
  );
}
