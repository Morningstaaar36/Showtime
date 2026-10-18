/** The static venue in 3D: an architectural model look (section-cut walls, ink edges). */
import { Edges, Line } from "@react-three/drei";
import type { ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import * as THREE from "three";
import type { Exit, Floor, Obstacle, Pt, StageParams, Stair, Venue, Zone } from "@/api/types";
import { isProposed, lockedIds } from "@/lib/annotations";
import { fmtInt, fmtNum } from "@/lib/format";
import { floorLabels } from "@/lib/venueOps";
import { exitName } from "@/lib/venueText";
import {
  bbox,
  centroid,
  doorwayOf,
  FENCE_M,
  floorY,
  shapeOf,
  stairProfile,
  stairRun,
  wallThickness,
  WALL_INDOOR_M,
  WALL_T,
  wallPieces,
} from "./geom";
import type { ScenePalette } from "./palette";
import { RouteLayer } from "./RouteLayer";
import { SceneHtml } from "./SceneHtml";

export interface ModelHandlers {
  onExitClick?: (exit: Exit, floor: Floor, e: ThreeEvent<MouseEvent>) => void;
  onObjectClick?: (kind: "obstacle" | "zone" | "stair" | "stage", id: string, floor: Floor, e: ThreeEvent<MouseEvent>) => void;
  onFloorClick?: (floor: Floor, x: number, y: number, e: ThreeEvent<MouseEvent>) => void;
  onFloorMove?: (floor: Floor, x: number, y: number) => void;
  onFloorDoubleClick?: (floor: Floor, x: number, y: number) => void;
  /** grab an object to drag it (doors, stage, features, crowd areas) */
  onObjectPointerDown?: (kind: "exit" | "obstacle" | "zone" | "stage", id: string, floor: Floor, e: ThreeEvent<PointerEvent>) => void;
}

interface Props extends ModelHandlers {
  venue: Venue;
  palette: ScenePalette;
  exploded: boolean;
  labels: boolean;
  showZones: boolean;
  selectedId: string | null;
  blocked: string[];
  dimOtherFloors?: string | null;
  peopleOverride?: Record<string, number>;
  /** venue sits on a street map: draw the ground floor see-through so the map shows */
  onMap?: boolean;
  /** ids allowed a label (see `labelledIds`); null or absent = every object */
  labelled?: Set<string> | null;
  /** stairs whose other floor is not drawn (one floor alone): shown as a stairwell outline */
  stubStairs?: Stair[];
  /** one floor drawn in full; the other storeys are ghosts (outlines and faint plates, no labels,
   * not clickable) and every stair is highlighted */
  focusFloor?: string | null;
  /** a tall building seen whole: room walls low, storeys as clean floor plates, stairs highlighted */
  stacked?: boolean;
}

/** Room walls of a tall building seen whole: a plan-drawing cut, low enough not to stack into ribs. */
const STACKED_WALL_M = 0.55;
/** Room walls of the floor in focus: cut at handrail height, so small rooms don't read as ribs. */
const FOCUS_WALL_M = 1.1;

const may = (p: Props, id: string) => p.labels && (!p.labelled || p.labelled.has(id));

const OBSTACLE_HEIGHT: Record<string, number> = {
  wall: WALL_INDOOR_M, booth: 2.6, bar: 2.4, seating: 0.55, column: 3.0, barrier: 1.1,
  fence: 1.2, other: 1.4, stage: 1.0,
};

export function VenueModel(props: Props) {
  const { venue, exploded } = props;
  const focus = props.focusFloor && venue.floors.some((f) => f.floor_id === props.focusFloor) ? props.focusFloor : null;
  const focusElev = venue.floors.find((f) => f.floor_id === focus)?.elevation_m ?? 0;
  const tags = useMemo(() => floorTags(venue), [venue]);
  const multi = venue.floors.length > 1 && (!!focus || !!props.stacked || exploded);
  return (
    <group>
      {venue.floors.map((f) => {
        const y = floorY(venue, f.floor_id, exploded);
        if (focus && f.floor_id !== focus) {
          return <GhostFloor key={f.floor_id} floor={f} y={y} palette={props.palette} above={(f.elevation_m ?? 0) > focusElev}
                             tag={exploded ? tags.get(f.floor_id) : undefined} />;
        }
        return <FloorGroup key={f.floor_id} {...props} floor={f} y={y} />;
      })}
      {/* stacked storeys sit too close for tags at the same corner: those floors are named in the lift panel */}
      {exploded && multi && venue.floors.filter((f) => !focus || f.floor_id === focus).map((f) => (
        <FloorTag key={`tag-${f.floor_id}`} floor={f} y={floorY(venue, f.floor_id, exploded)} text={tags.get(f.floor_id) ?? f.floor_id}
                  focus={f.floor_id === focus} />
      ))}
      {(venue.stairs ?? []).map((s) => (
        <StairMesh key={s.id} stair={s} venue={venue} palette={props.palette} exploded={exploded}
                   highlight={multi} selected={props.selectedId === s.id} labels={may(props, s.id)}
                   onClick={(e) => {
                     const fl = venue.floors.find((f) => f.floor_id === s.from_floor);
                     if (fl) props.onObjectClick?.("stair", s.id, fl, e);
                   }} />
      ))}
      {(props.stubStairs ?? []).map((s) => {
        const floor = venue.floors.find((f) => f.floor_id === s.from_floor || f.floor_id === s.to_floor);
        if (!floor) return null;
        return (
          <StairStub key={s.id} stair={s} floor={floor} y={floorY(venue, floor.floor_id, exploded)} palette={props.palette}
                     selected={props.selectedId === s.id} labels={may(props, s.id)}
                     onClick={(e) => props.onObjectClick?.("stair", s.id, floor, e)} />
        );
      })}
      <RouteLayer venue={venue} palette={props.palette} exploded={exploded} labels={props.labels} />
    </group>
  );
}

function FloorGroup(props: Props & { floor: Floor; y: number }) {
  const { floor, y, palette, venue } = props;
  const isUpper = (floor.elevation_m ?? 0) > 0.01;
  const dim = props.dimOtherFloors && props.dimOtherFloors !== floor.floor_id;
  const locked = useMemo(() => lockedIds(venue), [venue]);
  return (
    <group position={[0, y, 0]}>
      <Slab floor={floor} palette={palette} outdoor={venue.mode === "outdoor"} upper={isUpper}
            onClick={props.onFloorClick} onMove={props.onFloorMove} onDouble={props.onFloorDoubleClick}
            dim={!!dim} seeThrough={!!props.onMap && !isUpper} />
      <Walls floor={floor} palette={palette} outdoor={venue.mode === "outdoor"} upper={isUpper || !!props.stacked} />
      {isUpper && !props.exploded && (
        <BalconyStructure floor={floor} base={venue.floors[0]} height={y} palette={palette} />
      )}
      {floor.obstacles.map((o) => (
        o.kind === "stage" ? (
          <StageModel key={o.id} obstacle={o} stage={venue.stage ?? null} palette={palette}
                      selected={props.selectedId === o.id} labels={may(props, o.id)} venue={venue}
                      onClick={(e) => props.onObjectClick?.("stage", o.id, floor, e)}
                      onGrab={props.onObjectPointerDown && ((e) => props.onObjectPointerDown?.("stage", o.id, floor, e))} />
        ) : (
          <ObstacleMesh key={o.id} obstacle={o} palette={palette} selected={props.selectedId === o.id}
                        lowWalls={props.stacked ? STACKED_WALL_M : props.focusFloor ? FOCUS_WALL_M : undefined}
                        labels={may(props, o.id)} proposed={isProposed(venue, o.id)} locked={locked.has(o.id)}
                        onClick={(e) => props.onObjectClick?.("obstacle", o.id, floor, e)}
                        onGrab={props.onObjectPointerDown && ((e) => props.onObjectPointerDown?.("obstacle", o.id, floor, e))} />
        )
      ))}
      {floor.zones.map((z) => (
        <ZonePatch key={z.id} zone={z} palette={palette} selected={props.selectedId === z.id} labels={may(props, z.id)}
                   visible={props.showZones}
                   people={props.peopleOverride?.[z.id] ?? z.people}
                   onClick={(e) => props.onObjectClick?.("zone", z.id, floor, e)}
                   onGrab={props.onObjectPointerDown && ((e) => props.onObjectPointerDown?.("zone", z.id, floor, e))} />
      ))}
      {floor.exits.map((e) => (
        <ExitGate key={e.id} exit={e} floor={floor} palette={palette} outdoor={venue.mode === "outdoor"}
                  blocked={!!e.blocked || props.blocked.includes(e.id)} selected={props.selectedId === e.id}
                  proposed={isProposed(venue, e.id)} locked={locked.has(e.id)}
                  labels={may(props, e.id)} onClick={(ev) => props.onExitClick?.(e, floor, ev)}
                  onGrab={props.onObjectPointerDown && ((ev) => props.onObjectPointerDown?.("exit", e.id, floor, ev))} />
      ))}
    </group>
  );
}

function Slab({ floor, palette, outdoor, upper, onClick, onMove, onDouble, dim, seeThrough }: {
  floor: Floor; palette: ScenePalette; outdoor: boolean; upper: boolean; dim: boolean; seeThrough?: boolean;
  onClick?: ModelHandlers["onFloorClick"]; onMove?: ModelHandlers["onFloorMove"];
  onDouble?: ModelHandlers["onFloorDoubleClick"];
}) {
  const geo = useMemo(() => {
    const shape = shapeOf(floor.walkable as Pt[]);
    if (upper) {
      const g = new THREE.ExtrudeGeometry(shape, { depth: 0.3, bevelEnabled: false });
      g.rotateX(-Math.PI / 2);
      g.translate(0, -0.3, 0);
      return g;
    }
    const g = new THREE.ShapeGeometry(shape);
    g.rotateX(-Math.PI / 2);
    g.translate(0, 0.005, 0);
    return g;
  }, [floor.walkable, upper]);
  useEffect(() => () => geo.dispose(), [geo]);
  const outline = useMemo(() => [...(floor.walkable as Pt[]), floor.walkable[0] as Pt]
    .map((p) => new THREE.Vector3(p[0], 0.012, -p[1])), [floor.walkable]);
  const toVenue = (e: ThreeEvent<MouseEvent | PointerEvent>): [number, number] => [e.point.x, -e.point.z];
  return (
    <group>
      <mesh geometry={geo} receiveShadow
            onClick={(e) => { if (onClick) { e.stopPropagation(); const [x, y] = toVenue(e); onClick(floor, x, y, e); } }}
            onDoubleClick={(e) => { if (onDouble) { e.stopPropagation(); const [x, y] = toVenue(e); onDouble(floor, x, y); } }}
            onPointerMove={(e) => { if (onMove) { const [x, y] = toVenue(e); onMove(floor, x, y); } }}>
        <meshStandardMaterial color={outdoor ? palette.floorOutdoor : palette.floor} roughness={0.95}
                              metalness={0} transparent={dim || seeThrough} opacity={dim ? 0.25 : seeThrough ? 0.3 : 1}
                              depthWrite={!seeThrough} polygonOffset polygonOffsetFactor={-1} />
      </mesh>
      <Line points={outline} color={palette.slabEdge} lineWidth={1.2} transparent opacity={dim ? 0.2 : 0.9} />
    </group>
  );
}

function Walls({ floor, palette, outdoor, upper }: { floor: Floor; palette: ScenePalette; outdoor: boolean; upper: boolean }) {
  const pieces = useMemo(() => wallPieces(floor), [floor]);
  const h = outdoor ? FENCE_M : upper ? 1.1 : WALL_INDOOR_M;
  const t = outdoor ? 0.08 : upper ? 0.06 : WALL_T;
  return (
    <group>
      {pieces.map((p, i) => {
        const dx = p.b[0] - p.a[0];
        const dy = p.b[1] - p.a[1];
        const len = Math.hypot(dx, dy);
        const mx = (p.a[0] + p.b[0]) / 2 + p.edge.nx * t / 2;
        const my = (p.a[1] + p.b[1]) / 2 + p.edge.ny * t / 2;
        const rot = Math.atan2(dy, dx);
        return (
          <group key={i} position={[mx, 0, -my]} rotation={[0, rot, 0]}>
            <mesh position={[0, h / 2, 0]} castShadow receiveShadow>
              <boxGeometry args={[len + t, h, t]} />
              <meshStandardMaterial color={outdoor ? palette.barrier : palette.wall} roughness={0.85}
                                    transparent={outdoor || upper} opacity={outdoor ? 0.55 : upper ? 0.35 : 1} />
            </mesh>
            {!outdoor && !upper && (
              <mesh position={[0, h + 0.015, 0]}>
                <boxGeometry args={[len + t, 0.03, t + 0.002]} />
                <meshBasicMaterial color={palette.wallCut} />
              </mesh>
            )}
            {outdoor && <FencePosts len={len} h={h} color={palette.barrier} />}
          </group>
        );
      })}
    </group>
  );
}

/** Columns under the open edge of a balcony and a glass railing along it. */
function BalconyStructure({ floor, base, height, palette }: { floor: Floor; base: Floor; height: number; palette: ScenePalette }) {
  const edges = useMemo(() => {
    const outer = base.walkable as Pt[];
    const ring = floor.walkable as Pt[];
    const segDist = (p: Pt, a: Pt, b: Pt) => {
      const dx = b[0] - a[0], dy = b[1] - a[1];
      const t = Math.max(0, Math.min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy || 1)));
      return Math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy);
    };
    const toOuter = (p: Pt) => Math.min(...outer.map((a, i) => segDist(p, a, outer[(i + 1) % outer.length])));
    const out: [Pt, Pt][] = [];
    ring.forEach((a, i) => {
      const b = ring[(i + 1) % ring.length];
      const mid: Pt = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
      if (toOuter(mid) > 0.5) out.push([a, b]);
    });
    return out;
  }, [floor.walkable, base.walkable]);
  return (
    <group>
      {edges.map(([a, b], i) => {
        const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
        const rot = Math.atan2(b[1] - a[1], b[0] - a[0]);
        const n = Math.max(2, Math.round(len / 6) + 1);
        return (
          <group key={i}>
            {Array.from({ length: n }, (_, k) => {
              const t = n === 1 ? 0.5 : k / (n - 1);
              const x = a[0] + (b[0] - a[0]) * t, y = a[1] + (b[1] - a[1]) * t;
              return (
                <mesh key={k} position={[x, -(height + 0.3) / 2, -y]} castShadow>
                  <boxGeometry args={[0.35, Math.max(0.1, height - 0.3), 0.35]} />
                  <meshStandardMaterial color={palette.wall} roughness={0.8} />
                </mesh>
              );
            })}
            <mesh position={[(a[0] + b[0]) / 2, 0.55, -(a[1] + b[1]) / 2]} rotation={[0, rot, 0]}>
              <boxGeometry args={[len, 1.1, 0.04]} />
              <meshStandardMaterial color={palette.signal} transparent opacity={0.18} roughness={0.1} metalness={0.1} />
            </mesh>
            <mesh position={[(a[0] + b[0]) / 2, 1.1, -(a[1] + b[1]) / 2]} rotation={[0, rot, 0]}>
              <boxGeometry args={[len, 0.05, 0.08]} />
              <meshStandardMaterial color={palette.edge} roughness={0.5} metalness={0.4} />
            </mesh>
          </group>
        );
      })}
    </group>
  );
}

function FencePosts({ len, h, color }: { len: number; h: number; color: string }) {
  const n = Math.max(2, Math.floor(len / 5) + 1);
  return (
    <>
      {Array.from({ length: n }, (_, i) => (
        <mesh key={i} position={[-len / 2 + (len * i) / (n - 1), h / 2, 0]}>
          <boxGeometry args={[0.05, h + 0.05, 0.05]} />
          <meshStandardMaterial color={color} roughness={0.6} metalness={0.3} />
        </mesh>
      ))}
    </>
  );
}

function ObstacleMesh({ obstacle, palette, selected, labels, proposed, locked, lowWalls, onClick, onGrab }: {
  obstacle: Obstacle; palette: ScenePalette; selected: boolean; labels: boolean;
  /** draw room walls cut at this height (a tall building: plan-drawing cut) */
  lowWalls?: number;
  /** proposed construction: drawn see-through until it is built */
  proposed: boolean; locked: boolean;
  onClick: (e: ThreeEvent<MouseEvent>) => void;
  onGrab?: (e: ThreeEvent<PointerEvent>) => void;
}) {
  const full = obstacle.height_m ?? OBSTACLE_HEIGHT[obstacle.kind ?? "other"] ?? 1.4;
  const h = lowWalls && obstacle.kind === "wall" ? Math.min(full, lowWalls) : full;
  const geo = useMemo(() => {
    const g = new THREE.ExtrudeGeometry(shapeOf(obstacle.polygon as Pt[]), { depth: h, bevelEnabled: false });
    g.rotateX(-Math.PI / 2);
    return g;
  }, [obstacle.polygon, h]);
  useEffect(() => () => geo.dispose(), [geo]);
  const capGeo = useMemo(() => {
    const g = new THREE.ShapeGeometry(shapeOf(obstacle.polygon as Pt[]));
    g.rotateX(-Math.PI / 2);
    return g;
  }, [obstacle.polygon]);
  useEffect(() => () => capGeo.dispose(), [capGeo]);
  const ghost = (obstacle.label ?? obstacle.id).toLowerCase().includes("stair");
  const isWater = obstacle.id.startsWith("water_");
  const isWall = obstacle.kind === "wall";
  const isBarrier = obstacle.kind === "barrier" || obstacle.kind === "fence";
  const color = isWater ? "#7fb2e0" : isWall ? palette.wall : isBarrier ? palette.barrier
    : obstacle.kind === "booth" || obstacle.kind === "bar" ? palette.booth : palette.obstacle;
  const [cx, cy] = centroid(obstacle.polygon as Pt[]);
  // map imports number unnamed buildings ("Building 19"); those labels only crowd out the exits
  const generic = /^building \d+$/i.test(obstacle.label ?? "");
  const showLabel = labels && !ghost && (proposed || selected || (!isWall && !isBarrier && !generic));
  const see = ghost || isWater || proposed;
  if (isWall && obstacle.line && obstacle.line.length >= 2) {
    return <LineWall obstacle={obstacle} height={h} palette={palette} selected={selected} proposed={proposed} onClick={onClick} onGrab={onGrab} />;
  }
  return (
    <group>
      <mesh geometry={geo} castShadow receiveShadow onClick={(e) => { e.stopPropagation(); onClick(e); }}
            onPointerDown={onGrab && ((e) => { e.stopPropagation(); onGrab(e); })}
            onPointerOver={(e) => { e.stopPropagation(); document.body.style.cursor = "pointer"; }}
            onPointerOut={() => { document.body.style.cursor = ""; }}>
        <meshStandardMaterial color={color} roughness={isBarrier ? 0.5 : 0.85} metalness={isBarrier ? 0.35 : 0}
                              transparent={see} opacity={ghost ? 0.12 : isWater ? 0.85 : proposed ? 0.45 : 1} depthWrite={!ghost && !proposed}
                              emissive={selected ? palette.signal : "#000000"} emissiveIntensity={selected ? 0.25 : 0} />
        <Edges color={selected ? palette.signal : palette.edge} threshold={20} />
      </mesh>
      {isWall && (
        <mesh position={[0, h + 0.012, 0]} geometry={capGeo}>
          <meshBasicMaterial color={palette.wallCut} />
        </mesh>
      )}
      {showLabel && (
        <SceneHtml position={[cx, h + 0.4, -cy]} center zIndexRange={[20, 0]} style={{ pointerEvents: "none" }}>
          <div className="whitespace-nowrap rounded-[3px] bg-surface/90 px-1.5 py-0.5 text-2xs font-medium text-muted shadow-sm">
            {obstacle.label ?? obstacle.id}{proposed ? " · proposed" : ""}{locked ? " · locked" : ""}
          </div>
        </SceneHtml>
      )}
    </group>
  );
}

/** An inner wall drawn along its centreline: one straight box per segment at the wall's own
 * thickness, so thin partitions stay crisp instead of a buffered outline with rounded joints. */
function LineWall({ obstacle, height, palette, selected, proposed, onClick, onGrab }: {
  obstacle: Obstacle; height: number; palette: ScenePalette; selected: boolean; proposed: boolean;
  onClick: (e: ThreeEvent<MouseEvent>) => void; onGrab?: (e: ThreeEvent<PointerEvent>) => void;
}) {
  const line = obstacle.line as Pt[];
  const thick = wallThickness(obstacle.polygon as Pt[], line);
  const pieces = useMemo(() => line.slice(1).map((b, i) => {
    const a = line[i];
    const len = Math.hypot(b[0] - a[0], b[1] - a[1]);
    return { mx: (a[0] + b[0]) / 2, my: (a[1] + b[1]) / 2, len, rot: Math.atan2(b[1] - a[1], b[0] - a[0]) };
  }).filter((p) => p.len > 1e-3), [line]);
  return (
    <group onClick={(e) => { e.stopPropagation(); onClick(e); }}
           onPointerDown={onGrab && ((e) => { e.stopPropagation(); onGrab(e); })}>
      {pieces.map((p, i) => (
        <group key={i} position={[p.mx, 0, -p.my]} rotation={[0, p.rot, 0]}>
          <mesh position={[0, height / 2, 0]} castShadow receiveShadow>
            {/* overlap the joints by the thickness so corners close */}
            <boxGeometry args={[p.len + thick, height, thick]} />
            <meshStandardMaterial color={palette.wall} roughness={0.85} transparent={proposed} opacity={proposed ? 0.45 : 1}
                                  emissive={selected ? palette.signal : "#000000"} emissiveIntensity={selected ? 0.25 : 0} />
            <Edges color={selected ? palette.signal : palette.edge} threshold={20} />
          </mesh>
          <mesh position={[0, height + 0.012, 0]}>
            <boxGeometry args={[p.len + thick, 0.02, thick + 0.002]} />
            <meshBasicMaterial color={palette.wallCut} />
          </mesh>
        </group>
      ))}
    </group>
  );
}

function StageModel({ obstacle, stage, palette, selected, labels, venue, onClick, onGrab }: {
  obstacle: Obstacle; stage: StageParams | null; palette: ScenePalette; selected: boolean; labels: boolean;
  venue: Venue; onClick: (e: ThreeEvent<MouseEvent>) => void; onGrab?: (e: ThreeEvent<PointerEvent>) => void;
}) {
  const poly = obstacle.polygon as Pt[];
  const [x0, y0, x1, y1] = bbox(poly);
  const deckH = stage ? 1.5 : obstacle.height_m ?? 1.0;
  const deckGeo = useMemo(() => {
    const g = new THREE.ExtrudeGeometry(shapeOf(poly), { depth: deckH, bevelEnabled: false });
    g.rotateX(-Math.PI / 2);
    return g;
  }, [poly, deckH]);
  useEffect(() => () => deckGeo.dispose(), [deckGeo]);
  // which side faces the audience: the bbox side nearest the venue centre
  const [vx0, vy0, vx1, vy1] = bbox(venue.floors[0].walkable as Pt[]);
  const vcy = (vy0 + vy1) / 2;
  const frontIsSouth = (y0 + y1) / 2 > vcy;
  const roofH = stage?.roof_height_m ?? 0;
  const legs = stage ? Math.max(2, Math.floor(stage.legs / 2)) : 0;
  const bannerH = stage && stage.banner_area_m2 ? Math.min(roofH - deckH - 1, stage.banner_area_m2 / (x1 - x0)) : 0;
  const backY = frontIsSouth ? y1 : y0;
  const frame = palette.stageFrame;
  const [cx, cy] = [(x0 + x1) / 2, (y0 + y1) / 2];
  void vx0; void vx1;
  return (
    <group onClick={(e) => { e.stopPropagation(); onClick(e); }}
           onPointerDown={onGrab && ((e) => { e.stopPropagation(); onGrab(e); })}
           onPointerOver={(e) => { e.stopPropagation(); document.body.style.cursor = "pointer"; }}
           onPointerOut={() => { document.body.style.cursor = ""; }}>
      <mesh geometry={deckGeo} castShadow receiveShadow>
        <meshStandardMaterial color={palette.stageDeck} roughness={0.8}
                              emissive={selected ? palette.signal : "#000"} emissiveIntensity={selected ? 0.2 : 0} />
        <Edges color={selected ? palette.signal : palette.edge} threshold={20} />
      </mesh>
      {stage && roofH > deckH && (
        <group>
          {[y0, y1].flatMap((yy, row) =>
            Array.from({ length: legs }, (_, i) => {
              const xx = x0 + ((x1 - x0) * i) / (legs - 1);
              return (
                <mesh key={`${row}-${i}`} position={[xx, roofH / 2, -yy]} castShadow>
                  <boxGeometry args={[0.24, roofH, 0.24]} />
                  <meshStandardMaterial color={frame} roughness={0.5} metalness={0.5} />
                </mesh>
              );
            }),
          )}
          {/* roof truss: perimeter beams and cross beams */}
          {[y0, y1].map((yy, i) => (
            <mesh key={`b${i}`} position={[cx, roofH, -yy]} castShadow>
              <boxGeometry args={[x1 - x0 + 0.4, 0.42, 0.3]} />
              <meshStandardMaterial color={frame} roughness={0.5} metalness={0.5} />
            </mesh>
          ))}
          {Array.from({ length: legs }, (_, i) => {
            const xx = x0 + ((x1 - x0) * i) / (legs - 1);
            return (
              <mesh key={`c${i}`} position={[xx, roofH, -cy]} castShadow>
                <boxGeometry args={[0.22, 0.36, y1 - y0]} />
                <meshStandardMaterial color={frame} roughness={0.5} metalness={0.5} />
              </mesh>
            );
          })}
          <mesh position={[cx, roofH + 0.45, -cy]} rotation={[-Math.PI / 2, 0, 0]} castShadow>
            <planeGeometry args={[x1 - x0 + 1.2, y1 - y0 + 1.2]} />
            <meshStandardMaterial color={palette.membrane} roughness={0.9} transparent opacity={0.82}
                                  side={THREE.DoubleSide} />
          </mesh>
          {bannerH > 0.3 && (
            <mesh position={[cx, roofH - 0.3 - bannerH / 2, -backY]} castShadow>
              <planeGeometry args={[x1 - x0, bannerH]} />
              <meshStandardMaterial color={palette.membrane} roughness={0.9} side={THREE.DoubleSide}
                                    transparent opacity={0.9} />
            </mesh>
          )}
        </group>
      )}
      {labels && (
        <SceneHtml position={[cx, (stage ? roofH : deckH) + 1.2, -cy]} center zIndexRange={[20, 0]} style={{ pointerEvents: "none" }}>
          <div className="whitespace-nowrap rounded-[3px] bg-surface/90 px-1.5 py-0.5 text-2xs font-semibold text-ink shadow-sm">
            {obstacle.label ?? "Stage"}
          </div>
        </SceneHtml>
      )}
    </group>
  );
}

function ExitGate({ exit, floor, palette, outdoor, blocked, selected, proposed, locked, labels, onClick, onGrab }: {
  exit: Exit; floor: Floor; palette: ScenePalette; outdoor: boolean; blocked: boolean; selected: boolean;
  /** a proposed new opening, not yet built: drawn see-through */
  proposed: boolean; locked: boolean;
  labels: boolean; onClick: (e: ThreeEvent<MouseEvent>) => void; onGrab?: (e: ThreeEvent<PointerEvent>) => void;
}) {
  const door = useMemo(() => doorwayOf(floor.walkable as Pt[], exit), [floor.walkable, exit]);
  const color = blocked ? palette.danger : palette.egress;
  const h = outdoor ? 2.8 : 2.25;
  if (!door) {
    const [cx, cy] = centroid(exit.polygon as Pt[]);
    return (
      <mesh position={[cx, 1, -cy]} onClick={(e) => { e.stopPropagation(); onClick(e); }}
            onPointerDown={onGrab && ((e) => { e.stopPropagation(); onGrab(e); })}>
        <cylinderGeometry args={[0.25, 0.25, 2, 12]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={palette.night ? 2.4 : 0.4} />
      </mesh>
    );
  }
  const rot = Math.atan2(door.edge.uy, door.edge.ux);
  const half = door.width / 2;
  const post = outdoor ? 0.18 : 0.12;
  return (
    <group position={[door.cx, 0, -door.cy]} rotation={[0, rot, 0]}>
      {/* hit area: generous box over the opening */}
      <mesh position={[0, h / 2, 0]} onClick={(e) => { e.stopPropagation(); onClick(e); }}
            onPointerDown={onGrab && ((e) => { e.stopPropagation(); onGrab(e); })}
            onPointerOver={(e) => { e.stopPropagation(); document.body.style.cursor = "pointer"; }}
            onPointerOut={() => { document.body.style.cursor = ""; }}>
        <boxGeometry args={[door.width + 0.6, h + 0.4, 1.4]} />
        <meshBasicMaterial transparent opacity={0} depthWrite={false} />
      </mesh>
      {[-half, half].map((s) => (
        <mesh key={s} position={[s, h / 2, 0]} castShadow>
          <boxGeometry args={[post, h, post]} />
          <meshStandardMaterial color={color} emissive={color} emissiveIntensity={palette.night ? (blocked ? 1.6 : 2.6) : selected ? 0.7 : 0.35} roughness={0.4}
                                transparent={proposed} opacity={proposed ? 0.4 : 1} />
        </mesh>
      ))}
      <mesh position={[0, h, 0]} castShadow>
        <boxGeometry args={[door.width + post, post, post]} />
        <meshStandardMaterial color={color} emissive={color} emissiveIntensity={palette.night ? (blocked ? 1.6 : 2.6) : selected ? 0.7 : 0.35} roughness={0.4}
                                transparent={proposed} opacity={proposed ? 0.4 : 1} />
      </mesh>
      {blocked ? (
        <group position={[0, h / 2, 0]}>
          {[1, -1].map((s) => (
            <mesh key={s} rotation={[0, 0, s * Math.atan2(h, door.width)]}>
              <boxGeometry args={[Math.hypot(h, door.width) * 0.92, 0.12, 0.08]} />
              <meshStandardMaterial color={palette.danger} emissive={palette.danger} emissiveIntensity={0.6} />
            </mesh>
          ))}
        </group>
      ) : (
        <ExitArrow width={door.width} color={palette.egress} outward={door.edge} rot={rot} />
      )}
      {labels && (
        <SceneHtml position={[0, h + 0.7, 0]} center zIndexRange={[30, 0]} style={{ pointerEvents: "none" }}>
          <div className={`whitespace-nowrap rounded-[3px] px-1.5 py-0.5 text-2xs font-semibold shadow-sm tabular ${blocked ? "bg-danger-strong text-on-strong" : "bg-egress-strong text-on-strong"}`}>
            {exitName(floor, exit)} · {fmtNum(exit.width_m, 1)} m{blocked ? " · blocked" : ""}{proposed ? " · proposed" : ""}{locked ? " · locked" : ""}
          </div>
        </SceneHtml>
      )}
    </group>
  );
}

/** Flat arrow on the ground, just outside the door, pointing outward. */
function ExitArrow({ width, color, outward, rot }: { width: number; color: string; outward: { nx: number; ny: number }; rot: number }) {
  const geo = useMemo(() => {
    const L = Math.min(1.8, 0.6 + width * 0.35);
    const W = Math.min(1.2, width * 0.55);
    const s = new THREE.Shape();
    s.moveTo(-W * 0.25, 0); s.lineTo(W * 0.25, 0); s.lineTo(W * 0.25, L * 0.55); s.lineTo(W * 0.5, L * 0.55);
    s.lineTo(0, L); s.lineTo(-W * 0.5, L * 0.55); s.lineTo(-W * 0.25, L * 0.55); s.closePath();
    const g = new THREE.ShapeGeometry(s);
    g.rotateX(-Math.PI / 2); // arrow now points along local -Z
    return g;
  }, [width]);
  useEffect(() => () => geo.dispose(), [geo]);
  // outward normal (venue) -> world (nx, 0, -ny) -> gate frame (rotated by `rot` about Y)
  const lx = outward.nx * Math.cos(rot) + outward.ny * Math.sin(rot);
  const lz = outward.nx * Math.sin(rot) - outward.ny * Math.cos(rot);
  const phi = Math.atan2(-lx, -lz);
  return (
    <mesh geometry={geo} position={[lx * 0.35, 0.025, lz * 0.35]} rotation={[0, phi, 0]}>
      <meshBasicMaterial color={color} transparent opacity={0.85} />
    </mesh>
  );
}

function ZonePatch({ zone, palette, selected, labels, people, onClick, onGrab, visible }: {
  zone: Zone; palette: ScenePalette; selected: boolean; labels: boolean; people: number; visible: boolean;
  onClick: (e: ThreeEvent<MouseEvent>) => void; onGrab?: (e: ThreeEvent<PointerEvent>) => void;
}) {
  const geo = useMemo(() => {
    const g = new THREE.ShapeGeometry(shapeOf(zone.polygon as Pt[]));
    g.rotateX(-Math.PI / 2);
    return g;
  }, [zone.polygon]);
  useEffect(() => () => geo.dispose(), [geo]);
  const pts = useMemo(() => [...(zone.polygon as Pt[]), zone.polygon[0] as Pt]
    .map((p) => new THREE.Vector3(p[0], 0.03, -p[1])), [zone.polygon]);
  const [cx, cy] = centroid(zone.polygon as Pt[]);
  return (
    <group visible={visible}>
      <mesh geometry={geo} position={[0, 0.02, 0]} onClick={(e) => { e.stopPropagation(); onClick(e); }}
            onPointerDown={onGrab && ((e) => { e.stopPropagation(); onGrab(e); })}>
        <meshBasicMaterial color={palette.zone} transparent opacity={selected ? 0.16 : 0.07} depthWrite={false} />
      </mesh>
      <Line points={pts} color={palette.zone} lineWidth={selected ? 2 : 1.2} dashed dashSize={0.8} gapSize={0.5}
            transparent opacity={0.75} />
      {labels && (
        <SceneHtml position={[cx, 0.4, -cy]} center zIndexRange={[15, 0]} style={{ pointerEvents: "none", display: visible ? "block" : "none" }}>
          <div className="whitespace-nowrap rounded-[3px] border border-signal/30 bg-surface/85 px-1.5 py-0.5 text-2xs text-signal shadow-sm tabular">
            {zone.label ?? zone.id} · {fmtInt(people)}
          </div>
        </SceneHtml>
      )}
    </group>
  );
}

function StairMesh({ stair, venue, palette, exploded, selected, labels, highlight, onClick }: {
  stair: Stair; venue: Venue; palette: ScenePalette; exploded: boolean; selected: boolean; labels: boolean;
  /** several storeys in view: the stair is the way down, so it stands out */
  highlight?: boolean;
  onClick: (e: ThreeEvent<MouseEvent>) => void;
}) {
  const yTop = floorY(venue, stair.from_floor, exploded);
  const yBot = floorY(venue, stair.to_floor, exploded);
  const rise = yTop - yBot;
  const climb = useMemo(() => stairRun(stair.top_polygon as Pt[], stair.bottom_polygon as Pt[]), [stair.top_polygon, stair.bottom_polygon]);
  // the flight's side profile (steps over a soffit) extruded across the stair's width
  const geo = useMemo(() => {
    const g = new THREE.ExtrudeGeometry(shapeOf(stairProfile(climb.run, rise)), { depth: stair.width_m, bevelEnabled: false });
    g.translate(0, 0, -stair.width_m / 2);
    return g;
  }, [climb.run, rise, stair.width_m]);
  useEffect(() => () => geo.dispose(), [geo]);
  return (
    <group position={[climb.bx, yBot, -climb.by]} rotation={[0, climb.angle, 0]}
           onClick={(e) => { e.stopPropagation(); onClick(e); }}>
      <mesh geometry={geo} castShadow receiveShadow>
        <meshStandardMaterial color={selected ? palette.signal : highlight ? palette.stairHot : palette.stair} roughness={0.8}
                              emissive={highlight && !selected ? palette.stairHot : "#000000"} emissiveIntensity={highlight ? 0.25 : 0} />
        <Edges color={selected ? palette.signal : highlight ? palette.stairHot : palette.edge} threshold={30} />
      </mesh>
      {[-1, 1].map((s) => (
        <Line key={s} points={[new THREE.Vector3(0, 1.0, (s * stair.width_m) / 2),
                               new THREE.Vector3(climb.run, rise + 1.0, (s * stair.width_m) / 2)]}
              color={highlight ? palette.stairHot : palette.edge} lineWidth={highlight ? 2.5 : 1.5} />
      ))}
      {labels && (
        <SceneHtml position={[climb.run / 2, rise / 2 + 1.6, 0]} center zIndexRange={[15, 0]} style={{ pointerEvents: "none" }}>
          <div className="whitespace-nowrap rounded-[3px] bg-surface/90 px-1.5 py-0.5 text-2xs text-muted shadow-sm">
            Stair · {fmtNum(stair.width_m, 1)} m
          </div>
        </SceneHtml>
      )}
    </group>
  );
}

/** A stair seen from one floor alone: its landing on this floor, with an arrow up or down. */
function StairStub({ stair, floor, y, palette, selected, labels, onClick }: {
  stair: Stair; floor: Floor; y: number; palette: ScenePalette; selected: boolean; labels: boolean;
  onClick: (e: ThreeEvent<MouseEvent>) => void;
}) {
  const down = stair.from_floor === floor.floor_id;
  const poly = (down ? stair.top_polygon : stair.bottom_polygon) as Pt[];
  const geo = useMemo(() => {
    const g = new THREE.ShapeGeometry(shapeOf(poly));
    g.rotateX(-Math.PI / 2);
    return g;
  }, [poly]);
  useEffect(() => () => geo.dispose(), [geo]);
  const [cx, cy] = centroid(poly);
  const color = selected ? palette.signal : palette.stair;
  return (
    <group position={[0, y + 0.03, 0]}>
      <mesh geometry={geo} onClick={(e) => { e.stopPropagation(); onClick(e); }}>
        <meshStandardMaterial color={color} roughness={0.8} transparent opacity={0.85} />
      </mesh>
      <Line points={[...poly, poly[0]].map((p) => new THREE.Vector3(p[0], 0.02, -p[1]))} color={palette.edge} lineWidth={1.5} />
      {labels && (
        <SceneHtml position={[cx, 1.0, -cy]} center zIndexRange={[15, 0]} style={{ pointerEvents: "none" }}>
          <div className="whitespace-nowrap rounded-[3px] bg-surface/90 px-1.5 py-0.5 text-2xs text-muted shadow-sm">
            {down ? "Stairs down" : "Stairs up"} · {fmtNum(stair.width_m, 1)} m
          </div>
        </SceneHtml>
      )}
    </group>
  );
}

/** "2nd floor · 120" (the floor's name, else Ground / 1st / B1), for tags next to each storey. */
function floorTags(venue: Venue): Map<string, string> {
  const labels = floorLabels(venue);
  return new Map(venue.floors.map((f) => {
    const l = labels.get(f.floor_id) ?? f.floor_id;
    const name = f.name?.trim() || (l === "Ground" ? "Ground floor" : l.startsWith("B") ? l : `${l} floor`);
    return [f.floor_id, `${name} · ${fmtInt(f.zones.reduce((n, z) => n + z.people, 0))}`];
  }));
}

/** The storey's name at its corner, so a stack of floors reads like a section drawing. */
function FloorTag({ floor, y, text, focus }: { floor: Floor; y: number; text: string; focus: boolean }) {
  const [x0, y0] = bbox(floor.walkable as Pt[]);
  return (
    <SceneHtml position={[x0, y + 0.4, -y0]} zIndexRange={[12, 0]} style={{ pointerEvents: "none", transform: "translate(-105%, -50%)" }}>
      <div className={`whitespace-nowrap rounded-[4px] px-1.5 py-0.5 text-2xs font-semibold tabular shadow-sm ${focus ? "bg-signal text-signal-ink" : "bg-surface/90 text-muted"}`}>
        {text}
      </div>
    </SceneHtml>
  );
}

const NO_RAYCAST = () => null;

/** A storey out of focus: a faint plate with its outline and room walls as thin lines. Floors
 * above the focus are outlines only, so they never hide the floor in focus. Not clickable. */
function GhostFloor({ floor, y, palette, above, tag }: { floor: Floor; y: number; palette: ScenePalette; above: boolean; tag?: string }) {
  const geo = useMemo(() => {
    const g = new THREE.ShapeGeometry(shapeOf(floor.walkable as Pt[]));
    g.rotateX(-Math.PI / 2);
    return g;
  }, [floor.walkable]);
  useEffect(() => () => geo.dispose(), [geo]);
  const ring = useMemo(() => [...(floor.walkable as Pt[]), floor.walkable[0] as Pt].map((p) => new THREE.Vector3(p[0], 0.02, -p[1])), [floor.walkable]);
  const walls = useMemo(() => floor.obstacles.filter((o) => o.kind === "wall").map((o) => {
    const pts = (o.line && o.line.length >= 2 ? o.line : [...o.polygon, o.polygon[0]]) as Pt[];
    return pts.map((p) => new THREE.Vector3(p[0], 0.03, -p[1]));
  }), [floor.obstacles]);
  return (
    <group position={[0, y, 0]}>
      <mesh geometry={geo} raycast={NO_RAYCAST} renderOrder={-1}>
        <meshBasicMaterial color={palette.floor} transparent opacity={above ? 0.06 : 0.42} depthWrite={false} />
      </mesh>
      <Line points={ring} color={palette.slabEdge} lineWidth={above ? 1 : 1.4} transparent opacity={above ? 0.45 : 0.8} raycast={NO_RAYCAST} />
      {!above && walls.map((pts, i) => (
        <Line key={i} points={pts} color={palette.slabEdge} lineWidth={0.8} transparent opacity={0.45} raycast={NO_RAYCAST} />
      ))}
      {floor.exits.map((e) => {
        const [cx, cy] = centroid(e.polygon as Pt[]);
        return (
          <mesh key={e.id} position={[cx, 0.05, -cy]} raycast={NO_RAYCAST}>
            <cylinderGeometry args={[0.35, 0.35, 0.08, 12]} />
            <meshBasicMaterial color={palette.egress} transparent opacity={above ? 0.35 : 0.7} />
          </mesh>
        );
      })}
      {tag && (
        <SceneHtml position={[bbox(floor.walkable as Pt[])[0], 0.4, -bbox(floor.walkable as Pt[])[1]]} zIndexRange={[12, 0]}
                   style={{ pointerEvents: "none", transform: "translate(-105%, -50%)" }}>
          <div className="whitespace-nowrap rounded-[4px] bg-surface/90 px-1.5 py-0.5 text-2xs font-semibold text-muted tabular shadow-sm">{tag}</div>
        </SceneHtml>
      )}
    </group>
  );
}
