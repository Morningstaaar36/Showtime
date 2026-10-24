/** Real cases: documented crowd disasters the Designer agent rebuilds from their sourced
 * descriptions (GET /real_cases, POST /real_cases/{id}/open). A project built from one keeps
 * the case's facts in venue.extensions.real_case. */
import type { RunResult, Venue } from "@/api/types";

export interface CaseSource { label: string; url: string }

/** What a project keeps about its case (api/core/real_cases.py RealCase.card). */
export interface RealCaseCard {
  id: string;
  title: string;
  incident: string;
  date: string;
  place: string;
  deaths: number;
  toll: string;
  what_happened: string;
  lesson: string;
  sources: CaseSource[];
  approximations: string[];
}

/** A case as GET /real_cases lists it, with the project already built from it (if any). */
export interface RealCase extends RealCaseCard {
  description: string;
  dimensions: string[];
  project_id: string | null;
}

/** POST /real_cases/{id}/open */
export interface OpenCaseOut {
  project_id: string;
  session_id: string | null;
  status: "testing" | "existing" | "needs_fixes" | "failed";
  problems?: string[];
}

/** Where to go once a case is open: watch its test, fix its layout, or see its plan. */
export function openTarget(out: OpenCaseOut): string {
  if (out.status === "testing" && out.session_id) return `/p/${out.project_id}/work?session=${out.session_id}&live=1`;
  if (out.status === "needs_fixes" || !out.session_id) return `/p/${out.project_id}/describe`;
  return `/p/${out.project_id}`;
}

const isSource = (s: unknown): s is CaseSource =>
  !!s && typeof s === "object" && typeof (s as CaseSource).url === "string" && /^https?:\/\//.test((s as CaseSource).url)
  && typeof (s as CaseSource).label === "string";

/** The case a venue was built from, or null (also for a malformed block). */
export function realCaseOf(venue: Venue | null | undefined): RealCaseCard | null {
  const raw = (venue?.extensions as Record<string, unknown> | undefined)?.real_case;
  if (!raw || typeof raw !== "object") return null;
  const c = raw as Partial<RealCaseCard>;
  if (typeof c.id !== "string" || typeof c.what_happened !== "string" || typeof c.title !== "string") return null;
  return {
    id: c.id,
    title: c.title,
    incident: c.incident ?? c.title,
    date: c.date ?? "",
    place: c.place ?? "",
    deaths: typeof c.deaths === "number" ? c.deaths : 0,
    toll: c.toll ?? "",
    what_happened: c.what_happened,
    lesson: c.lesson ?? "",
    sources: Array.isArray(c.sources) ? c.sources.filter(isSource) : [],
    approximations: Array.isArray(c.approximations) ? c.approximations.filter((a): a is string => typeof a === "string") : [],
  };
}

function inside(pt: [number, number], poly: [number, number][]): boolean {
  let hit = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    if ((yi > pt[1]) !== (yj > pt[1]) && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}

/** The run's worst spot in words: peak density and where it was (the exit it was near, else
 * the zone or passage it lies in, else nothing). */
export function simulatedPeak(run: RunResult | null | undefined, venue: Venue | null | undefined,
                              label: (id: string) => string): { peak: number; where: string | null } | null {
  const spots = [...(run?.hotspots ?? [])].sort((a, b) => b.peak_density_ppm2 - a.peak_density_ppm2);
  const top = spots[0];
  const peak = run?.metrics?.peak_density_ppm2 ?? top?.peak_density_ppm2;
  if (typeof peak !== "number" || !Number.isFinite(peak) || peak <= 0) return null;
  if (!top) return { peak, where: null };
  if (top.near) return { peak, where: label(top.near) };
  const floor = venue?.floors.find((f) => f.floor_id === top.floor_id) ?? venue?.floors[0];
  const zone = floor?.zones.find((z) => inside([top.x, top.y], z.polygon as [number, number][]));
  return { peak, where: zone ? (zone.label ?? label(zone.id)) : null };
}
