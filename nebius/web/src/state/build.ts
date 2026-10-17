/** Options of the building-editor tools (door width, stair size, room door side…). View state only:
 * what they build is saved as a patch. Kept per browser tab, reset when the page reloads. */
import { create } from "zustand";
import type { BuildOptions } from "@/lib/buildTools";
import { DEFAULT_BUILD_OPTIONS } from "@/lib/buildTools";

interface BuildState {
  opts: BuildOptions;
  setOpt: <K extends keyof BuildOptions>(k: K, v: BuildOptions[K]) => void;
  reset: () => void;
}

export const useBuild = create<BuildState>((set) => ({
  opts: DEFAULT_BUILD_OPTIONS,
  setOpt: (k, v) => set((s) => ({ opts: { ...s.opts, [k]: v } })),
  reset: () => set({ opts: DEFAULT_BUILD_OPTIONS }),
}));
