import { Volume2, VolumeX } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import type { Pt, RunResult, Venue, WhatIfOut } from "@/api/types";
import { t } from "@/i18n";
import { fmtInt } from "@/lib/format";
import { exitName } from "@/lib/venueText";
import { bbox, centroid, floorsBottomUp, floorY, venueBounds } from "@/scene/geom";
import { useUi } from "@/state/ui";

interface Shot { pos: [number, number, number]; target: [number, number, number]; caption: string; ms?: number }

export function buildShots(venue: Venue, run: RunResult | null | undefined, what: WhatIfOut | null): Shot[] {
  const [x0, y0, x1, y1] = venueBounds(venue);
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, span = Math.max(x1 - x0, y1 - y0, 20);
  const people = venue.floors.reduce((n, f) => n + f.zones.reduce((m, z) => m + z.people, 0), 0);
  const exits = venue.floors.flatMap((f) => f.exits.map((e) => ({ f, e })));
  const shots: Shot[] = [{
    pos: [cx - span * 0.35, span * 0.95, -cy + span * 0.95], target: [cx, 0, -cy],
    caption: t(venue.floors.length > 1 ? "tour.overview_floors" : "tour.overview", {
      name: venue.name, mode: t(venue.mode === "indoor" ? "tour.indoor" : "tour.open_air"), people: fmtInt(people),
      exits: exits.length === 1 ? t("tour.exits_one") : t("tour.exits", { n: exits.length }), floors: venue.floors.length,
    }),
  }];
  // a building: how the floors are joined, and how many people are on each
  const stairs = venue.stairs ?? [];
  if (venue.floors.length > 1 && stairs.length) {
    const narrow = [...stairs].sort((a, b) => a.width_m - b.width_m)[0];
    const [sx, sy] = centroid(narrow.top_polygon as Pt[]);
    const y = floorY(venue, narrow.to_floor, false);
    const perFloor = floorsBottomUp(venue).map((f) => t("tour.floor_people", { name: f.name || f.floor_id, n: fmtInt(f.zones.reduce((n, z) => n + z.people, 0)) })).join(", ");
    shots.push({
      pos: [sx + 16, y + 16, -sy + 16], target: [sx, y + 2, -sy],
      caption: t(stairs.length === 1 ? "tour.stairs_one" : "tour.stairs", { n: stairs.length, w: narrow.width_m.toFixed(1), floors: perFloor }),
      ms: 5200,
    });
  }
  // who is in the crowd, when the plan says (patients, children, wheelchair users…)
  const mix = new Map<string, number>();
  for (const f of venue.floors) for (const z of f.zones) for (const g of z.groups ?? []) {
    if (g.kind !== "general" && g.share > 0) mix.set(g.kind, (mix.get(g.kind) ?? 0) + Math.round(g.share * z.people));
  }
  if (mix.size) {
    const who = [...mix.entries()].sort((a, b) => b[1] - a[1]).map(([k, n]) => t("tour.group", { n: fmtInt(n), kind: t(`editor.people.${k}`).toLowerCase() })).join(", ");
    shots.push({ pos: [cx - span * 0.5, span * 0.7, -cy + span * 0.5], target: [cx, 0, -cy], caption: t("tour.mix", { who }) });
  }
  for (const f of venue.floors) {
    const stage = f.obstacles.find((o) => o.kind === "stage");
    if (!stage) continue;
    const [sx, sy] = centroid(stage.polygon as Pt[]);
    const [a, b, c, d] = bbox(stage.polygon as Pt[]);
    const crowd = f.zones.length ? centroid(f.zones.flatMap((z) => z.polygon as Pt[])) : [cx, cy];
    const dx = crowd[0] - sx, dy = crowd[1] - sy, L = Math.hypot(dx, dy) || 1;
    const y = floorY(venue, f.floor_id, false);
    shots.push({
      pos: [sx + (dx / L) * 28, y + 14, -(sy + (dy / L) * 28)], target: [sx, y + 2, -sy],
      caption: t("tour.stage", { w: Math.round(Math.max(c - a, d - b)) }),
    });
    break;
  }
  for (const { f, e } of [...exits].sort((p, q) => q.e.width_m - p.e.width_m).slice(0, 2)) {
    const [ex, ey] = centroid(e.polygon as Pt[]);
    const y = floorY(venue, f.floor_id, false);
    const dx = ex - cx, dy = ey - cy, L = Math.hypot(dx, dy) || 1;
    shots.push({
      pos: [ex - (dx / L) * 22, y + 11, -(ey - (dy / L) * 22)], target: [ex, y + 1, -ey],
      caption: t(e.blocked ? "tour.exit_closed" : "tour.exit", { name: exitName(f, e), w: e.width_m.toFixed(1) }), ms: 3800,
    });
  }
  const hot = (run?.hotspots ?? [])[0];
  if (hot) {
    const y = floorY(venue, hot.floor_id, false);
    shots.push({
      pos: [hot.x + 12, y + 14, -hot.y + 14], target: [hot.x, y, -hot.y],
      caption: t("tour.hotspot", { d: hot.peak_density_ppm2.toFixed(1), at: `${Math.floor(hot.t_s / 60)}:${String(Math.round(hot.t_s % 60)).padStart(2, "0")}` }),
    });
  }
  const m = what?.metrics ?? run?.metrics;
  const end: string[] = [];
  if (m?.evac_time_p95_s) end.push(t("tour.evac", { m: Math.floor(m.evac_time_p95_s / 60), s: Math.round(m.evac_time_p95_s % 60) }));
  if (what) end.push(t("tour.score", { n: fmtInt(what.capacity.safe_people), grade: what.score.grade, score: what.score.score }));
  shots.push({ pos: [cx + span * 0.6, span * 0.75, -cy + span * 0.6], target: [cx, 0, -cy], caption: end.join(" ") || t("tour.end"), ms: 5200 });
  return shots;
}

export interface Tour { playing: boolean; play: () => void; stop: () => void; overlay: ReactNode }

/** A narrated camera tour of the plan: overview, stage, exits, the densest spot, the verdict.
 * Returns the controls (the View menu starts it) and the caption overlay to render once. */
export function useTour({ projectId, version, venue, run, autoStart }: { projectId: string; version: number; venue: Venue | undefined; run: RunResult | null | undefined; autoStart?: boolean }): Tour {
  const setShot = useUi((s) => s.setShot);
  const [caption, setCaption] = useState<string | null>(null);
  const [step, setStep] = useState(0);
  const [count, setCount] = useState(0);
  const [muted, setMuted] = useState(false);
  const alive = useRef(0);
  const started = useRef(false);

  const stop = useCallback(() => {
    alive.current += 1;
    window.speechSynthesis?.cancel();
    setCaption(null);
  }, []);

  const play = useCallback(async () => {
    if (!venue) return;
    const id = ++alive.current;
    let what: WhatIfOut | null = null;
    try {
      what = await api.post<WhatIfOut>(`/projects/${projectId}/whatif`, { version, run_id: run?.tier === 3 ? run.run_id : null });
    } catch { /* the tour still runs without the score */ }
    const shots = buildShots(venue, run, what);
    setCount(shots.length);
    for (let i = 0; i < shots.length; i++) {
      if (id !== alive.current) return;
      const s = shots[i];
      setStep(i);
      setCaption(s.caption);
      setShot(s.pos, s.target);
      const spoke = new Promise<void>((resolve) => {
        const synth = window.speechSynthesis;
        if (muted || !synth) { resolve(); return; }
        const u = new SpeechSynthesisUtterance(s.caption);
        u.rate = 1.02;
        u.onend = () => resolve();
        u.onerror = () => resolve();
        synth.cancel();
        synth.speak(u);
      });
      await Promise.all([spoke, new Promise((r) => setTimeout(r, s.ms ?? 4200))]);
    }
    if (id === alive.current) setTimeout(() => { if (id === alive.current) setCaption(null); }, 400);
  }, [projectId, version, venue, run, muted, setShot]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") stop(); };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); stop(); };
  }, [stop]);
  // start once (?tour=1) when the venue is there, with the latest data at that moment
  const latest = useRef(play);
  useEffect(() => { latest.current = play; }, [play]);
  const ready = !!venue;
  useEffect(() => {
    if (!autoStart || !ready || started.current) return;
    started.current = true;
    const h = setTimeout(() => void latest.current(), 1500);
    return () => clearTimeout(h);
  }, [autoStart, ready]);

  const overlay = caption ? (
    <>
      <div className="pointer-events-none fixed inset-x-0 top-0 z-30 h-14 bg-gradient-to-b from-black/60 to-transparent" />
      <div className="pointer-events-none fixed inset-x-0 bottom-0 z-30 h-40 bg-gradient-to-t from-black/70 to-transparent" />
      <div className="pointer-events-auto fixed inset-x-0 bottom-10 z-40 flex justify-center px-6">
        <div role="status" aria-live="polite" className="max-w-2xl rounded-[var(--radius-panel)] bg-black/60 px-5 py-3 text-center text-white shadow-2xl backdrop-blur">
          <p className="text-[17px] leading-snug">{caption}</p>
          <div className="mt-2 flex items-center justify-center gap-3">
            <div className="flex gap-1" aria-hidden>{Array.from({ length: count }, (_, i) => <span key={i} className={`h-1 w-5 rounded-full ${i <= step ? "bg-white" : "bg-white/30"}`} />)}</div>
            <button type="button" className="grid size-9 place-items-center rounded-full text-white/85 hover:bg-white/10 hover:text-white"
                    onClick={() => { setMuted((m) => !m); window.speechSynthesis?.cancel(); }} aria-label={muted ? t("workspace.tour_unmute") : t("workspace.tour_mute")}>
              {muted ? <VolumeX className="size-4" /> : <Volume2 className="size-4" />}
            </button>
            <button type="button" className="min-h-9 rounded-full px-3 text-sm text-white/85 underline hover:text-white" onClick={stop}>{t("workspace.tour_stop")}</button>
          </div>
        </div>
      </div>
    </>
  ) : null;
  return { playing: caption !== null, play: () => void play(), stop, overlay };
}
