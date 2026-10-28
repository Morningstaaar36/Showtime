/** Options of the building-editor tools (door width, stair size, room door side…). View state only:
 * what they build is saved as a patch. Kept per browser tab, reset when the page reloads. Only
 * what the organizer changed is kept, so the rest follows the server's editor defaults. */
import { useMemo } from "react";
import { create } from "zustand";
import { type BuildOptions, buildOptionsOf } from "@/lib/buildTools";
import { useEditorDefaults } from "@/lib/useEditorDefaults";

interface BuildState {
  chosen: Partial<BuildOptions>;
  setOpt: <K extends keyof BuildOptions>(k: K, v: BuildOptions[K]) => void;
  reset: () => void;
}

export const useBuild = create<BuildState>((set) => ({
  chosen: {},
  setOpt: (k, v) => set((s) => ({ chosen: { ...s.chosen, [k]: v } })),
  reset: () => set({ chosen: {} }),
}));

/** The options the tools use now: the organizer's choices over the editor defaults. */
export function useBuildOptions(): BuildOptions {
  const ed = useEditorDefaults();
  const chosen = useBuild((s) => s.chosen);
  return useMemo(() => buildOptionsOf(ed, chosen), [ed, chosen]);
}
