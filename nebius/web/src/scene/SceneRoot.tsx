/** The 3D viewport: lights, ground grid, venue model, replay layers, edit tools, effects. */
import { Grid } from "@react-three/drei";
import { Canvas, type ThreeEvent } from "@react-three/fiber";
import { Bloom, EffectComposer, N8AO, SMAA, Vignette } from "@react-three/postprocessing";
import { type ReactNode, Suspense, useMemo, useRef, useState } from "react";
import type { Exit, Floor, Hotspot, Venue } from "@/api/types";
import type { ObjectChange } from "@/lib/venueDiff";
import type { Replay } from "@/replay/useReplay";
import { isBuildTool, useUi } from "@/state/ui";
import { CameraRig } from "./CameraRig";
import { ChangeHighlights, DraftPreview, MoveGizmo } from "./EditTools";
import { resolveFloorView, venueBounds } from "./geom";
import { useScenePalette } from "./palette";
import { labelledIds } from "./labels";
import { LabelLayer } from "./SceneHtml";
import { Agents, DensityLayer, Hotspots, Marshals, PlaybackClock, type MarshalNote } from "./ReplayLayers";
import { ShowLights } from "./ShowLights";
import { osmSite, SiteContext } from "./SiteContext";
import { VenueModel } from "./VenueModel";

export interface SceneProps {
  venue: Venue;
  replay: Replay | null;
  hotspots: Hotspot[];
  marshals: MarshalNote[];
  editable: boolean;
  resetNonce: number;
  quality: "high" | "low";
  onExitClick: (exit: Exit, floor: Floor) => void;
  onObjectClick: (kind: "obstacle" | "zone" | "stair" | "stage", id: string, floor: Floor) => void;
  onFloorClick: (floor: Floor, x: number, y: number) => void;
  onFloorDoubleClick: (floor: Floor, x: number, y: number) => void;
  onMove: (id: string, dx: number, dy: number) => void;
  onHotspot: (h: Hotspot) => void;
  peopleOverride?: Record<string, number>;
  /** only one canvas drives the replay clock (split-screen compare) */
  clock?: boolean;
  /** outlines of a proposal's changes (added, changed, removed objects) */
  highlights?: ObjectChange[];
  /** direct drag: grab an object to move it (replaces the arrow gizmo) */
  onObjectPointerDown?: (kind: "exit" | "obstacle" | "zone" | "stage", id: string, floor: Floor, e: ThreeEvent<PointerEvent>) => void;
  /** extra scene content (drag previews) rendered inside the canvas */
  children?: ReactNode;
}

export function SceneRoot(p: SceneProps) {
  const layers = useUi((s) => s.layers);
  const palette = useScenePalette(layers.night);
  const selection = useUi((s) => s.selection);
  const blocked = useUi((s) => s.blockedExits);
  const tool = useUi((s) => s.tool);
  const [cursor, setCursor] = useState<{ floorId: string; x: number; y: number } | null>(null);
  const [x0, y0, x1, y1] = useMemo(() => venueBounds(p.venue), [p.venue]);
  const span = Math.max(x1 - x0, y1 - y0, 20);
  const cx = (x0 + x1) / 2;
  const cy = (y0 + y1) / 2;
  const drawing = tool !== "select" && tool !== "block";
  // building tools draw over doors, walls and crowd areas: a click on them is a click on the floor there
  const building = p.editable && isBuildTool(tool);
  const asFloorClick = (f: Floor, e: ThreeEvent<MouseEvent>) => p.onFloorClick(f, e.point.x, -e.point.z);
  const showAgents = layers.people && p.replay;
  const site = useMemo(() => osmSite(p.venue), [p.venue]);
  const labelLayer = useRef<HTMLDivElement>(null);
  // one floor alone: the model, hotspots and highlights see a venue holding only that floor;
  // people and the heatmap keep the full venue (their floor indexes) and skip the others
  const floorView = useUi((s) => s.floorView);
  const view = resolveFloorView(p.venue, floorView);
  const onlyFloor = view === "all" || view === "exploded" ? null : view;
  const shown = useMemo<Venue>(() => {
    const floor = onlyFloor ? p.venue.floors.find((f) => f.floor_id === onlyFloor) : undefined;
    if (!floor) return p.venue;
    return { ...p.venue, floors: [floor], stairs: [], routes: (p.venue.routes ?? []).filter((r) => r.floor_id === floor.floor_id) };
  }, [p.venue, onlyFloor]);
  // one floor alone: its stairs show as landings ("Stairs down", "Stairs up")
  const stubStairs = useMemo(() => (onlyFloor ? (p.venue.stairs ?? []).filter((s) => s.from_floor === onlyFloor || s.to_floor === onlyFloor) : []),
    [p.venue, onlyFloor]);
  const editFloor = useUi((s) => s.editFloor);
  const labelled = useMemo(() => labelledIds(p.venue, view, editFloor), [p.venue, view, editFloor]);
  const hotspots = onlyFloor ? p.hotspots.filter((h) => h.floor_id === onlyFloor) : p.hotspots;

  return (
    <LabelLayer.Provider value={labelLayer}>
    <Canvas
      shadows
      dpr={[1, 1.75]}
      gl={{ antialias: false, powerPreference: "high-performance", preserveDrawingBuffer: true, logarithmicDepthBuffer: true }}
      camera={{ fov: 38, near: 0.5, far: Math.max(3000, span * 6), position: [cx + span, span, -cy + span] }}
      onPointerMissed={() => useUi.getState().select(null)}
      aria-label="3D view of the venue"
    >
      <color attach="background" args={[palette.bg]} />
      <fog attach="fog" args={[palette.bg, span * 3.5, span * 8]} />
      <hemisphereLight args={[palette.dark ? "#9fb3c8" : "#ffffff", palette.dark ? "#1a2228" : "#c9d3da", palette.night ? 0.12 : palette.dark ? 0.55 : 0.85]} />
      <ambientLight intensity={palette.night ? 0.06 : palette.dark ? 0.15 : 0.25} />
      <directionalLight
        position={[cx + span * 0.5, span * 0.9, -cy + span * 0.6]}
        intensity={palette.night ? 0.35 : palette.dark ? 1.1 : 1.6}
        color={palette.night ? "#8fa8ff" : "#ffffff"}
        castShadow
        shadow-mapSize={[2048, 2048]}
        shadow-bias={-0.0004}
        shadow-camera-left={-span * 0.8}
        shadow-camera-right={span * 0.8}
        shadow-camera-top={span * 0.8}
        shadow-camera-bottom={-span * 0.8}
        shadow-camera-far={span * 4}
      >
        <object3D attach="target" position={[cx, 0, -cy]} />
      </directionalLight>

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[cx, -0.03, -cy]} receiveShadow>
        <planeGeometry args={[span * 12, span * 12]} />
        <meshStandardMaterial color={palette.ground} roughness={1} />
      </mesh>
      {layers.grid && !site && (
        <Grid position={[cx, -0.015, -cy]} args={[span * 4, span * 4]} cellSize={1} sectionSize={10}
              cellThickness={0.6} sectionThickness={1.1} cellColor={palette.grid} sectionColor={palette.gridSection}
              fadeDistance={span * 5} fadeStrength={1} infiniteGrid={false} />
      )}

      <Suspense fallback={null}>
        {site && <SiteContext venue={p.venue} palette={palette} show={{ map: true, neighbours: true }} />}
        {layers.night && <ShowLights venue={shown} exploded={layers.exploded} />}
        <VenueModel
          venue={shown}
          palette={palette}
          onMap={!!site}
          exploded={layers.exploded}
          labels={layers.labels}
          labelled={labelled}
          stubStairs={stubStairs}
          showZones={layers.zones && !showAgents}
          selectedId={selection?.id ?? null}
          blocked={blocked}
          peopleOverride={p.peopleOverride}
          onExitClick={(e, f, ev: ThreeEvent<MouseEvent>) => { ev.stopPropagation(); if (building) asFloorClick(f, ev); else p.onExitClick(e, f); }}
          onObjectClick={(k, id, f, ev) => { if (building) asFloorClick(f, ev); else p.onObjectClick(k, id, f); }}
          onFloorClick={(f, x, y) => p.onFloorClick(f, x, y)}
          onFloorDoubleClick={(f, x, y) => p.onFloorDoubleClick(f, x, y)}
          onFloorMove={drawing ? (f, x, y) => setCursor({ floorId: f.floor_id, x, y }) : undefined}
          onObjectPointerDown={p.editable && tool === "select" ? p.onObjectPointerDown : undefined}
        />
        {p.replay && p.clock !== false && <PlaybackClock />}
        {showAgents && p.replay && (
          <Agents traj={p.replay.traj} density={p.replay.density} venue={p.venue} exploded={layers.exploded} palette={palette}
                  onlyFloor={onlyFloor} kinds={p.replay.kinds} />
        )}
        {p.replay?.density && (layers.heatmap || layers.terrain) && (
          <DensityLayer density={p.replay.density} venue={p.venue} exploded={layers.exploded} palette={palette}
                        terrain={layers.terrain} onlyFloor={onlyFloor} />
        )}
        {hotspots.length > 0 && (
          <Hotspots hotspots={hotspots} venue={shown} exploded={layers.exploded} palette={palette}
                    labels={layers.labels} selectedKey={selection?.kind === "hotspot" ? selection.id : null}
                    showAll={!p.replay} onSelect={(h) => p.onHotspot(h)} />
        )}
        {p.marshals.length > 0 && <Marshals notes={onlyFloor ? p.marshals.filter((m) => m.floor_id === onlyFloor) : p.marshals}
                                              venue={shown} exploded={layers.exploded} />}
        {p.editable && tool === "select" && !p.onObjectPointerDown && (
          <MoveGizmo venue={shown} exploded={layers.exploded} palette={palette} onMove={p.onMove} />
        )}
        {p.highlights && p.highlights.length > 0 && (
          <ChangeHighlights venue={shown} changes={onlyFloor ? p.highlights.filter((c) => c.floorId === onlyFloor) : p.highlights} exploded={layers.exploded} palette={palette} />
        )}
        {p.editable && drawing && (
          <DraftPreview venue={p.venue} exploded={layers.exploded} palette={palette} cursor={cursor} />
        )}
        {p.children}
      </Suspense>

      <CameraRig venue={p.venue} resetNonce={p.resetNonce} exploded={layers.exploded} />

      {p.quality === "high" && (
        <EffectComposer multisampling={0} enableNormalPass={false}>
          <N8AO aoRadius={1.8} intensity={palette.dark ? 2.2 : 1.6} distanceFalloff={0.8} halfRes quality="performance" />
          <Bloom luminanceThreshold={palette.night ? 0.35 : 0.82} luminanceSmoothing={0.2} intensity={palette.night ? 1.1 : 0.35} mipmapBlur />
          <Vignette offset={0.25} darkness={palette.dark ? 0.45 : 0.18} />
          <SMAA />
        </EffectComposer>
      )}
    </Canvas>
    {/* 3D labels (SceneHtml) live here: same origin and clipping as the canvas */}
    <div ref={labelLayer} className="pointer-events-none absolute inset-0 overflow-hidden [&>*]:pointer-events-auto" />
    {site && (
      <span className="pointer-events-none absolute bottom-1 right-2 z-10 text-[10px] text-muted">
        Map and data © OpenStreetMap contributors
      </span>
    )}
    </LabelLayer.Provider>
  );
}
