/** Real cases: documented crowd disasters the Designer agent rebuilds from their sourced
 * descriptions (GET /real_cases, POST /real_cases/{id}/open). A project built from one keeps
 * the case's facts in venue.extensions.real_case. */
import type { RunResult, Venue } from "@/api/types";
import type { EventKindId } from "@/lib/venueOps";

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

/** What an organizer writes to save a case (api/core/real_cases.py CaseFacts); the server
 * makes the id from the title. */
export interface CaseFacts {
  title: string;
  incident: string;
  date: string;
  place: string;
  deaths: number;
  people: number;
  toll: string;
  event_kind: EventKindId;
  location: { lat: number; lon: number; timezone: string };
  description: string;
  what_happened: string;
  lesson: string;
  sources: CaseSource[];
  dimensions: string[];
  approximations: string[];
}

/** A case as GET /real_cases lists it: a shipped example or one an organizer saved, with the
 * project already built from it (if any). */
export interface RealCase extends RealCaseCard, Omit<CaseFacts, keyof RealCaseCard> {
  origin: "example" | "saved";
  project_id: string | null;
}

/** The facts of a case, to edit it or to start a new case from a copy of it. */
export function factsOf(c: RealCase): CaseFacts {
  return {
    title: c.title, incident: c.incident, date: c.date, place: c.place, deaths: c.deaths, people: c.people,
    toll: c.toll, event_kind: c.event_kind, location: { ...c.location }, description: c.description,
    what_happened: c.what_happened, lesson: c.lesson, sources: c.sources.map((s) => ({ ...s })),
    dimensions: [...c.dimensions], approximations: [...c.approximations],
  };
}

/** A blank case for the form (nothing about any incident is assumed). */
export const blankFacts = (): CaseFacts => ({
  title: "", incident: "", date: "", place: "", deaths: 0, people: 0, toll: "", event_kind: "other",
  location: { lat: 0, lon: 0, timezone: "UTC" }, description: "", what_happened: "", lesson: "",
  sources: [{ label: "", url: "" }], dimensions: [], approximations: [],
});

/** One entry per non-empty line (dimensions, approximations). */
export const linesOf = (text: string) => text.split("\n").map((l) => l.trim()).filter(Boolean);

/** The first field the server would refuse as missing or too short, so the form can say so
 * at once (the server checks everything again). */
export function missingField(f: CaseFacts): keyof CaseFacts | null {
  const short: [keyof CaseFacts, number][] = [["title", 3], ["incident", 3], ["place", 2], ["toll", 1], ["description", 40], ["what_happened", 10], ["lesson", 5]];
  for (const [k, n] of short) if (String(f[k]).trim().length < n) return k;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(f.date)) return "date";
  if (f.location.lat === 0 && f.location.lon === 0) return "location"; // not found or entered yet
  if (f.people < 1) return "people";
  if (!f.sources.some((s) => /^https?:\/\/\S+\.\S+/.test(s.url.trim()) && s.label.trim().length >= 3)) return "sources";
  if (!f.dimensions.length) return "dimensions";
  if (!f.approximations.length) return "approximations";
  return null;
}

/** The form field a server validation error is about ("sources.0.url" → "sources"). */
export function fieldOfError(details: Record<string, unknown> | undefined): string | null {
  const errors = details?.errors;
  if (!Array.isArray(errors) || !errors.length) return null;
  const loc = (errors[0] as { loc?: unknown }).loc;
  return Array.isArray(loc) && typeof loc[1] === "string" ? loc[1] : null;
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
