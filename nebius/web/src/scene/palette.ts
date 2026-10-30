/** 3D material colours derived from the design tokens; follows the light/dark theme. */
import { useEffect, useState } from "react";

export interface ScenePalette {
  dark: boolean;
  /** "Showtime lights": event-night scene with stage lighting */
  night?: boolean;
  bg: string;
  ground: string;
  grid: string;
  gridSection: string;
  floor: string;
  floorOutdoor: string;
  slabEdge: string;
  wall: string;
  wallCut: string;
  edge: string;
  obstacle: string;
  booth: string;
  stageDeck: string;
  stageFrame: string;
  membrane: string;
  barrier: string;
  zone: string;
  signal: string;
  egress: string;
  caution: string;
  danger: string;
  agent: string;
  ink: string;
  stair: string;
  /** stairs when several storeys are in view: the way down stands out */
  stairHot: string;
  /** a multi-storey building's facade: window glass, the solid band between windows, frames */
  glass: string;
  spandrel: string;
  mullion: string;
  /** the roof deck over the top floor */
  roof: string;
  /** fixtures recognised by their label (see `fixtureOf`) */
  kitchen: string;
  kitchenFloor: string;
  toilets: string;
  /** WC pans, basins and cubicle partitions */
  sanitary: string;
  lift: string;
  table: string;
  chair: string;
  counter: string;
}

export const LIGHT_PALETTE: ScenePalette = {
  dark: false,
  bg: "#eef0ff",
  ground: "#e9ecfd",
  grid: "#d4d8f5",
  gridSection: "#b9bfe9",
  floor: "#ffffff",
  floorOutdoor: "#e7f7e3",
  slabEdge: "#9aa0c3",
  wall: "#e9e8ff",
  wallCut: "#2b2870",
  edge: "#5d5fa0",
  obstacle: "#ffd9b8",
  booth: "#ffe3a8",
  stageDeck: "#c9c2ff",
  stageFrame: "#5b4ff5",
  membrane: "#ffffff",
  barrier: "#f2711c",
  zone: "#5b4ff5",
  signal: "#5b4ff5",
  egress: "#0f9d58",
  caution: "#d98200",
  danger: "#e03e4c",
  agent: "#3a3f8f",
  ink: "#1d1b3a",
  stair: "#b9c6ff",
  stairHot: "#0a9fe0",
  glass: "#9cc6e6",
  spandrel: "#c3c6e8",
  mullion: "#6a6da6",
  roof: "#d6d8ef",
  kitchen: "#cfd6df",
  kitchenFloor: "#e4e9ee",
  toilets: "#bfe2f4",
  sanitary: "#f7f8fc",
  lift: "#a3abbb",
  table: "#c89b6c",
  chair: "#7e78b0",
  counter: "#b98b60",
};

const DARK: ScenePalette = {
  dark: true,
  bg: "#17163a",
  ground: "#302f6a",
  grid: "#2b2a55",
  gridSection: "#3a397a",
  floor: "#262552",
  floorOutdoor: "#1d2c3a",
  slabEdge: "#5d5c94",
  wall: "#34335f",
  wallCut: "#d9d8ff",
  edge: "#8a89c0",
  obstacle: "#3b3a68",
  booth: "#46457b",
  stageDeck: "#4a4890",
  stageFrame: "#9aa7b1",
  membrane: "#d9e1e6",
  barrier: "#8996a0",
  zone: "#6b9eea",
  signal: "#6b9eea",
  egress: "#35b57c",
  caution: "#e2a72a",
  danger: "#f05a57",
  agent: "#c4ced5",
  ink: "#e5ebee",
  stair: "#4a4a86",
  stairHot: "#4cc3ff",
  glass: "#6f9fca",
  spandrel: "#2a2950",
  mullion: "#8a89c0",
  roof: "#2f2e5e",
  kitchen: "#5c6679",
  kitchenFloor: "#2e3152",
  toilets: "#3f6d88",
  sanitary: "#b9c0d6",
  lift: "#7f899c",
  table: "#8c6b4d",
  chair: "#55548c",
  counter: "#7c5b40",
};

const NIGHT: ScenePalette = {
  ...DARK,
  night: true,
  bg: "#04060c",
  ground: "#06090f",
  grid: "#0f1620",
  gridSection: "#16202c",
  floor: "#0d1218",
  floorOutdoor: "#0b1210",
  wall: "#1b232b",
  obstacle: "#1d252d",
  booth: "#232c35",
  stageDeck: "#1c2229",
  glass: "#3c5d7d",
  spandrel: "#141b22",
  mullion: "#2b3642",
  roof: "#151c23",
  kitchen: "#2a323c",
  kitchenFloor: "#11171d",
  toilets: "#1f3949",
  sanitary: "#3a4250",
  lift: "#3c4552",
  table: "#4a3a2b",
  chair: "#262d3a",
  counter: "#41311f",
};

function isDark(): boolean {
  return document.documentElement.classList.contains("dark");
}

/** Current palette; re-renders when the theme class on <html> changes. */
export function useScenePalette(night = false): ScenePalette {
  const [dark, setDark] = useState(isDark);
  useEffect(() => {
    const obs = new MutationObserver(() => setDark(isDark()));
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return night ? NIGHT : dark ? DARK : LIGHT_PALETTE;
}
