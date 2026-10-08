/** The 3D viewport: lights, ground grid, venue model, replay layers, edit tools, effects. */
import { Grid } from "@react-three/drei";
import { Canvas, type ThreeEvent } from "@react-three/fiber";
import { Bloom, EffectComposer, N8AO, SMAA, Vignette } from "@react-three/postprocessing";
import { Suspense, useMemo, useState } from "react";
import type { Exit, Floor, Hotspot, Venue } from "@/api/types";
import type { Replay } from "@/replay/useReplay";
import { useUi } from "@/state/ui";
import { CameraRig } from "./CameraRig";
import { DraftPreview, MoveGizmo } from "./EditTools";
import { venueBounds } from "./geom";
import { useScenePalette } from "./palette";
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
  const showAgents = layers.people && p.replay;
  const site = useMemo(() => osmSite(p.venue), [p.venue]);

  return (
    <>
    <Canvas
      shadows
      dpr={[1, 1.75]}
      gl={{ antialias: false, powerPreference: "high-performance", preserveDrawingBuffer: true, logarithmicDepthBuffer: true }}
      camera={{ fov: 38, near: 0.5, far: 3000, position: [cx + span, span, -cy + span] }}
      onPointerMissed={() => useUi.getState().select(null)}
      aria-label="3D view of the venue"
    >
      <color attach="background" args={[palette.bg]} />
      <fog attach="fog" args={[palette.bg, span * 2.2, span * 5]} />
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
        {layers.night && <ShowLights venue={p.venue} exploded={layers.exploded} />}
        <VenueModel
          venue={p.venue}
          palette={palette}
          onMap={!!site}
          exploded={layers.exploded}
          labels={layers.labels}
          showZones={layers.zones && !showAgents}
          selectedId={selection?.id ?? null}
          blocked={blocked}
          peopleOverride={p.peopleOverride}
          onExitClick={(e, f, ev: ThreeEvent<MouseEvent>) => { ev.stopPropagation(); p.onExitClick(e, f); }}
          onObjectClick={(k, id, f) => p.onObjectClick(k, id, f)}
          onFloorClick={(f, x, y) => p.onFloorClick(f, x, y)}
          onFloorDoubleClick={(f, x, y) => p.onFloorDoubleClick(f, x, y)}
          onFloorMove={drawing ? (f, x, y) => setCursor({ floorId: f.floor_id, x, y }) : undefined}
        />
        {p.replay && p.clock !== false && <PlaybackClock />}
        {showAgents && p.replay && (
          <Agents traj={p.replay.traj} density={p.replay.density} venue={p.venue} exploded={layers.exploded} palette={palette} />
        )}
        {p.replay?.density && (layers.heatmap || layers.terrain) && (
          <DensityLayer density={p.replay.density} venue={p.venue} exploded={layers.exploded} palette={palette}
                        terrain={layers.terrain} />
        )}
        {p.hotspots.length > 0 && (
          <Hotspots hotspots={p.hotspots} venue={p.venue} exploded={layers.exploded} palette={palette}
                    labels={layers.labels} selectedKey={selection?.kind === "hotspot" ? selection.id : null}
                    showAll={!p.replay} onSelect={(h) => p.onHotspot(h)} />
        )}
        {p.marshals.length > 0 && <Marshals notes={p.marshals} venue={p.venue} exploded={layers.exploded} />}
        {p.editable && tool === "select" && (
          <MoveGizmo venue={p.venue} exploded={layers.exploded} palette={palette} onMove={p.onMove} />
        )}
        {p.editable && drawing && (
          <DraftPreview venue={p.venue} exploded={layers.exploded} palette={palette} cursor={cursor} />
        )}
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
    {site && (
      <span className="pointer-events-none absolute bottom-1 right-2 z-10 text-[10px] text-muted">
        Map and data © OpenStreetMap contributors
      </span>
    )}
    </>
  );
}
