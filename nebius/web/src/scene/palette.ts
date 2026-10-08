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
}

const LIGHT: ScenePalette = {
  dark: false,
  bg: "#e9eef1",
  ground: "#e3e9ed",
  grid: "#cbd4db",
  gridSection: "#aab6bf",
  floor: "#fbfcfc",
  floorOutdoor: "#eef3ec",
  slabEdge: "#8e9ba5",
  wall: "#e6ebee",
  wallCut: "#1c2329",
  edge: "#5a6772",
  obstacle: "#d8dfe4",
  booth: "#cfd8de",
  stageDeck: "#c5ced5",
  stageFrame: "#6c7a85",
  membrane: "#ffffff",
  barrier: "#6f7c86",
  zone: "#1f5fbf",
  signal: "#1f5fbf",
  egress: "#0a7f4f",
  caution: "#b97f00",
  danger: "#c62828",
  agent: "#4a5866",
  ink: "#1c2329",
  stair: "#b8c3cb",
};

const DARK: ScenePalette = {
  dark: true,
  bg: "#10161a",
  ground: "#121a1f",
  grid: "#1f2a32",
  gridSection: "#2b3944",
  floor: "#1c252b",
  floorOutdoor: "#1a2320",
  slabEdge: "#4f5e69",
  wall: "#2a353d",
  wallCut: "#c9d2d8",
  edge: "#7d8b96",
  obstacle: "#2f3a43",
  booth: "#34414b",
  stageDeck: "#3a4752",
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
  stair: "#45535e",
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
  return night ? NIGHT : dark ? DARK : LIGHT;
}
