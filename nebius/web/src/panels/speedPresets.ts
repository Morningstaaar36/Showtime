/** The walking-speed choices of the what-if lab: the server's table (`effective.speed_presets`),
 * the one "Ask anything" uses too, so picking "rain" here and typing "in the rain" there test the
 * same speed. */
import { useMemo } from "react";
import { useSettings } from "@/api/queries";

export interface SpeedPreset {
  key: string;
  /** share of the normal walking speed */
  factor: number;
}

/** Used only until the settings arrive: the server's table (api/core/scenarios.py). */
const FALLBACK: readonly SpeedPreset[] = [
  { key: "normal", factor: 1 }, { key: "rain", factor: 0.85 }, { key: "families", factor: 0.75 }, { key: "smoke", factor: 0.5 },
];

/** Speed presets from the effective settings (`GET /settings`), in the server's order. */
export function speedPresetsOf(eff: Record<string, unknown>): SpeedPreset[] {
  const raw = eff.speed_presets;
  const out = typeof raw === "object" && raw !== null
    ? Object.entries(raw as Record<string, unknown>)
      .filter((e): e is [string, number] => typeof e[1] === "number" && e[1] > 0)
      .map(([key, factor]) => ({ key, factor }))
    : [];
  return out.length ? out : [...FALLBACK];
}

export function useSpeedPresets(): SpeedPreset[] {
  const eff = useSettings().data?.effective;
  return useMemo(() => speedPresetsOf(eff ?? {}), [eff]);
}
