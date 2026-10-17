/** Walking routes (marches, processions) on the floor: a band as wide as the route, a centre line
 * and chevrons pointing in walking order, with the route's name at its start. */
import { Line } from "@react-three/drei";
import { useLayoutEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { Pt, Venue } from "@/api/types";
import { floorY, polylineLength, routeMarks } from "./geom";
import type { ScenePalette } from "./palette";
import { SceneHtml } from "./SceneHtml";

type Route = NonNullable<Venue["routes"]>[number];

/** Chevron spacing: about 40 along the route, never closer than 2 m. */
export const chevronSpacing = (length: number): number => Math.max(2, length / 40);

const CHEVRON = (() => {
  const s = new THREE.Shape();
  s.moveTo(0.45, 0); s.lineTo(-0.35, 0.4); s.lineTo(-0.15, 0); s.lineTo(-0.35, -0.4); s.closePath();
  const g = new THREE.ShapeGeometry(s);
  g.rotateX(-Math.PI / 2);
  return g;
})();

function Chevrons({ points, y, color, scale }: { points: Pt[]; y: number; color: string; scale: number }) {
  const marks = useMemo(() => routeMarks(points, chevronSpacing(polylineLength(points))), [points]);
  const ref = useRef<THREE.InstancedMesh>(null);
  useLayoutEffect(() => {
    const m = ref.current;
    if (!m) return;
    const o = new THREE.Object3D();
    marks.forEach((k, i) => {
      o.position.set(k.x, y, -k.y);
      o.rotation.set(0, k.angle, 0);
      o.scale.setScalar(scale);
      o.updateMatrix();
      m.setMatrixAt(i, o.matrix);
    });
    m.count = marks.length;
    m.instanceMatrix.needsUpdate = true;
  }, [marks, y, scale]);
  if (!marks.length) return null;
  return (
    <instancedMesh ref={ref} args={[CHEVRON, undefined, marks.length]} renderOrder={3}>
      <meshBasicMaterial color={color} depthWrite={false} transparent opacity={0.95} />
    </instancedMesh>
  );
}

function RouteMark({ route, y, palette, labels }: { route: Route; y: number; palette: ScenePalette; labels: boolean }) {
  const pts = route.points as Pt[];
  const line = useMemo(() => pts.map((p) => new THREE.Vector3(p[0], y + 0.05, -p[1])), [pts, y]);
  const width = route.width_m ?? 0;
  const scale = Math.max(1, Math.min(4, (width || 2) / 2));
  return (
    <group>
      {width > 0 && <Line points={line} color={palette.signal} lineWidth={width} worldUnits transparent opacity={0.18} depthWrite={false} />}
      <Line points={line} color={palette.signal} lineWidth={2} dashed dashSize={0.8} gapSize={0.5} />
      <Chevrons points={pts} y={y + 0.07} color={palette.signal} scale={scale} />
      {labels && (
        <SceneHtml position={[pts[0][0], y + 1.2, -pts[0][1]]} center zIndexRange={[15, 0]} style={{ pointerEvents: "none" }}>
          <div className="whitespace-nowrap rounded-[3px] bg-signal px-1.5 py-0.5 text-2xs font-semibold text-signal-ink shadow-sm">
            {route.label || route.id}
          </div>
        </SceneHtml>
      )}
    </group>
  );
}

export function RouteLayer({ venue, palette, exploded, labels }: { venue: Venue; palette: ScenePalette; exploded: boolean; labels: boolean }) {
  const floors = new Set(venue.floors.map((f) => f.floor_id));
  const routes = (venue.routes ?? []).filter((r) => floors.has(r.floor_id) && r.points.length >= 2);
  return (
    <group>
      {routes.map((r) => <RouteMark key={r.id} route={r} y={floorY(venue, r.floor_id, exploded)} palette={palette} labels={labels} />)}
    </group>
  );
}
