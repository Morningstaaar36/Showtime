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
