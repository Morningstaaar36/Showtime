/** UI state (Zustand). Server state lives in TanStack Query; this is only view state. */
import { create } from "zustand";
import type { RunResult, VenuePatch } from "@/api/types";
import type { Units } from "@/lib/format";

export type Mode = "plan" | "simulate" | "redteam" | "report" | "analysis";
export type Tool = "select" | "exit" | "barrier" | "zone" | "block" | "measure" | BuildTool;
/** Building-editor tools (feat/editor): they act on `editFloor`. */
export type BuildTool = "wall" | "door" | "room" | "stair" | "route";
const BUILD_TOOLS: readonly BuildTool[] = ["wall", "door", "room", "stair", "route"];
export const isBuildTool = (t: Tool): t is BuildTool => (BUILD_TOOLS as readonly Tool[]).includes(t);
type Theme = "light" | "dark" | "system";

export interface Selection {
  kind: "obstacle" | "exit" | "zone" | "stair" | "hotspot" | "stage";
  id: string;
  floorId: string;
  x?: number;
  y?: number;
}

/** Which floors the 3D view shows: all stacked, spread apart, or one floor in focus (its id) with
 * the others ghosted. "auto" focuses the lowest floor of a tall building, else shows all. */
type FloorView = "auto" | "all" | "exploded" | (string & {});

export interface Layers {
  people: boolean;
  heatmap: boolean;
  terrain: boolean;
  labels: boolean;
  /** mirrors `floorView === "exploded"` for the scene parts that read it; set the floor view instead */
  exploded: boolean;
  zones: boolean;
  grid: boolean;
  /** "Showtime lights": the event night, with stage lighting */
  night: boolean;
}

interface UiState {
  theme: Theme;
  units: Units;
  tool: Tool;
  selection: Selection | null;
  hover: Selection | null;
  layers: Layers;
  activeRunId: string | null;
  compareRunId: string | null;
  blockedExits: string[];
  tier1Preview: RunResult | null;
  draft: [number, number][];
  proposal: VenuePatch | null;
  focusFloor: string | null;
  floorView: FloorView;
  flyTo: { x: number; y: number; floorId: string; nonce: number } | null;
  /** cinematic camera move (tour): position and target in scene coordinates */
  shot: { pos: [number, number, number]; target: [number, number, number]; nonce: number } | null;
  setShot: (pos: [number, number, number], target: [number, number, number]) => void;
  inspectorOpen: boolean;
  setTheme: (t: Theme) => void;
  setUnits: (u: Units) => void;
  setTool: (t: Tool) => void;
  select: (s: Selection | null) => void;
  setHover: (s: Selection | null) => void;
  toggleLayer: (k: keyof Layers, v?: boolean) => void;
  setActiveRun: (id: string | null) => void;
  setCompareRun: (id: string | null) => void;
  toggleBlocked: (exitId: string) => void;
  clearBlocked: () => void;
  setTier1Preview: (r: RunResult | null) => void;
  setDraft: (pts: [number, number][]) => void;
  setProposal: (p: VenuePatch | null) => void;
  setFocusFloor: (f: string | null) => void;
  setFloorView: (v: FloorView) => void;
  flyToPoint: (x: number, y: number, floorId: string) => void;
  setInspectorOpen: (v: boolean) => void;
  resetForProject: () => void;

  // --- building editor (feat/editor) ---
  /** floor the building tools act on; null = the ground (lowest) floor */
  editFloor: string | null;
  setEditFloor: (floorId: string | null) => void;
}

const PREFS_KEY = "showtime.prefs.v1";

function loadPrefs(): Partial<Pick<UiState, "theme" | "units" | "layers">> {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    return raw ? (JSON.parse(raw) as Partial<Pick<UiState, "theme" | "units" | "layers">>) : {};
  } catch {
    return {};
  }
}

function savePrefs(s: Pick<UiState, "theme" | "units" | "layers">): void {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify({ theme: s.theme, units: s.units, layers: s.layers }));
  } catch {
    /* private mode or blocked storage: preferences simply are not remembered */
  }
}

const DEFAULT_LAYERS: Layers = {
  people: true, heatmap: true, terrain: false, labels: true, exploded: false, zones: true, grid: true,
  night: false,
};

const prefs = loadPrefs();

export const useUi = create<UiState>((set, get) => ({
  theme: prefs.theme ?? "light", // bright by default; dark only when the organizer picks it
  units: prefs.units ?? "metric",
  tool: "select",
  selection: null,
  hover: null,
  layers: { ...DEFAULT_LAYERS, ...(prefs.layers ?? {}) },
  activeRunId: null,
  compareRunId: null,
  blockedExits: [],
  tier1Preview: null,
  draft: [],
  proposal: null,
  focusFloor: null,
  floorView: prefs.layers?.exploded ? "exploded" : "auto",
  flyTo: null,
  shot: null,
  setShot: (pos, target) => set((s) => ({ shot: { pos, target, nonce: (s.shot?.nonce ?? 0) + 1 } })),
  inspectorOpen: true,
  setTheme: (theme) => { set({ theme }); savePrefs(get()); },
  setUnits: (units) => { set({ units }); savePrefs(get()); },
  setTool: (tool) => set({ tool, draft: [] }),
  select: (selection) => set({ selection }),
  setHover: (hover) => set({ hover }),
  toggleLayer: (k, v) => {
    set((s) => {
      const on = v ?? !s.layers[k];
      const layers = { ...s.layers, [k]: on };
      if (k !== "exploded") return { layers };
      return { layers, floorView: on ? "exploded" : s.floorView === "exploded" ? "auto" : s.floorView };
    });
    savePrefs(get());
  },
  setActiveRun: (activeRunId) => set({ activeRunId }),
  setCompareRun: (compareRunId) => set({ compareRunId }),
  toggleBlocked: (id) =>
    set((s) => ({ blockedExits: s.blockedExits.includes(id) ? s.blockedExits.filter((e) => e !== id)
                                                              : [...s.blockedExits, id] })),
  clearBlocked: () => set({ blockedExits: [], tier1Preview: null }),
  setTier1Preview: (tier1Preview) => set({ tier1Preview }),
  setDraft: (draft) => set({ draft }),
  setProposal: (proposal) => set({ proposal }),
  setFocusFloor: (focusFloor) => set({ focusFloor }),
  setFloorView: (floorView) => {
    set((s) => ({ floorView, layers: { ...s.layers, exploded: floorView === "exploded" } }));
    savePrefs(get());
  },
  flyToPoint: (x, y, floorId) => set({ flyTo: { x, y, floorId, nonce: Date.now() } }),
  setInspectorOpen: (inspectorOpen) => set({ inspectorOpen }),
  resetForProject: () =>
    set((s) => ({ selection: null, hover: null, activeRunId: null, compareRunId: null, blockedExits: [],
          tier1Preview: null, draft: [], proposal: null, focusFloor: null, tool: "select", editFloor: null,
          // a floor id belongs to one venue; the exploded preference carries over
          floorView: s.floorView === "exploded" ? "exploded" : "auto" })),

  // --- building editor (feat/editor) ---
  editFloor: null,
  setEditFloor: (editFloor) => set({ editFloor, draft: [] }),
}));
