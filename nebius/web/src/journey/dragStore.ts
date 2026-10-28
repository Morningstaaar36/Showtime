/** Drag-and-drop state shared by the HTML palette and the 3D scene (two React renderers). */
import { create } from "zustand";
import type { GrabKind, Hit, PaletteItem } from "./dragDrop";

/** Screen point to venue coordinates on a floor (the top floor under the pointer wins). */
type Picker = (clientX: number, clientY: number, floorId?: string) => Hit | null;

export interface Grab {
  kind: GrabKind;
  id: string;
  floorId: string;
  start: [number, number];
  client: [number, number];
  /** becomes true once the pointer has moved far enough to be a drag, not a click */
  active: boolean;
  locked: boolean;
}

interface DragState {
  /** palette item being dragged */
  item: PaletteItem | null;
  /** palette item clicked (not dragged): the next click on the venue places it */
  armed: PaletteItem | null;
  grab: Grab | null;
  pointer: [number, number] | null;
  hit: Hit | null;
  pick: Picker | null;
  controls: { enabled: boolean } | null;
  set: (p: Partial<Omit<DragState, "set" | "reset">>) => void;
  reset: () => void;
}

export const useDrag = create<DragState>((set, get) => ({
  item: null,
  armed: null,
  grab: null,
  pointer: null,
  hit: null,
  pick: null,
  controls: null,
  set: (p) => set(p),
  reset: () => {
    const c = get().controls;
    if (c) c.enabled = true;
    set({ item: null, armed: null, grab: null, pointer: null, hit: null });
  },
}));
