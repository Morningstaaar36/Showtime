import { Clapperboard, Square, Volume2, VolumeX } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import type { Pt, RunResult, Venue, WhatIfOut } from "@/api/types";
import { Button } from "@/components/ui/button";
import { fmtInt } from "@/lib/format";
import { exitName } from "@/lib/venueText";
import { bbox, centroid, floorY, venueBounds } from "@/scene/geom";
import { useUi } from "@/state/ui";

interface Shot { pos: [number, number, number]; target: [number, number, number]; caption: string; ms?: number }

const mmss = (s: number) => `${Math.floor(s / 60)} minutes ${Math.round(s % 60)} seconds`;

function buildShots(venue: Venue, run: RunResult | null | undefined, what: WhatIfOut | null): Shot[] {
  const [x0, y0, x1, y1] = venueBounds(venue);
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2, span = Math.max(x1 - x0, y1 - y0, 20);
  const people = venue.floors.reduce((n, f) => n + f.zones.reduce((m, z) => m + z.people, 0), 0);
  const exits = venue.floors.flatMap((f) => f.exits.map((e) => ({ f, e })));
  const shots: Shot[] = [{
    pos: [cx - span * 0.35, span * 0.95, -cy + span * 0.95], target: [cx, 0, -cy],
    caption: `${venue.name}. An ${venue.mode === "indoor" ? "indoor" : "open-air"} plan for ${fmtInt(people)} people, with ${exits.length} exits.`,
  }];
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
      caption: `The stage, ${Math.round(Math.max(c - a, d - b))} metres wide, faces the crowd. Stewards keep the front-of-stage area clear.`,
    });
    break;
  }
  for (const { f, e } of [...exits].sort((p, q) => q.e.width_m - p.e.width_m).slice(0, 2)) {
    const [ex, ey] = centroid(e.polygon as Pt[]);
    const y = floorY(venue, f.floor_id, false);
    const dx = ex - cx, dy = ey - cy, L = Math.hypot(dx, dy) || 1;
    shots.push({
      pos: [ex - (dx / L) * 22, y + 11, -(ey - (dy / L) * 22)], target: [ex, y + 1, -ey],
      caption: `${exitName(f, e)}, ${e.width_m.toFixed(1)} metres wide${e.blocked ? ", closed in this plan" : ""}.`, ms: 3800,
    });
  }
  const hot = (run?.hotspots ?? [])[0];
  if (hot) {
    const y = floorY(venue, hot.floor_id, false);
    shots.push({
      pos: [hot.x + 12, y + 14, -hot.y + 14], target: [hot.x, y, -hot.y],
      caption: `The crowd is densest here: ${hot.peak_density_ppm2.toFixed(1)} people per square metre at ${Math.floor(hot.t_s / 60)}:${String(Math.round(hot.t_s % 60)).padStart(2, "0")}.`,
    });
  }
  const m = what?.metrics ?? run?.metrics;
  const end: string[] = [];
  if (m?.evac_time_p95_s) end.push(`95 percent of people are out in ${mmss(m.evac_time_p95_s)}.`);
  if (what) end.push(`Safe capacity is ${fmtInt(what.capacity.safe_people)}. Planning score ${what.score.grade}, ${what.score.score} out of 100.`);
  shots.push({ pos: [cx + span * 0.6, span * 0.75, -cy + span * 0.6], target: [cx, 0, -cy], caption: end.join(" ") || "That is the plan.", ms: 5200 });
  return shots;
}

/** A narrated camera tour of the plan: overview, stage, exits, the densest spot, the verdict. */
export function TourButton({ projectId, version, venue, run, autoStart }: { projectId: string; version: number; venue: Venue; run: RunResult | null | undefined; autoStart?: boolean }) {
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
  useEffect(() => {
    if (autoStart && !started.current) { started.current = true; const h = setTimeout(() => void play(), 1500); return () => clearTimeout(h); }
  }, [autoStart, play]);

  return (
    <>
      <Button size="sm" className="pointer-events-auto bg-surface/95 shadow-sm" onClick={() => (caption ? stop() : void play())}
              aria-label={caption ? "Stop the tour" : "Play a narrated tour of the plan"}>
        {caption ? <Square /> : <Clapperboard />}{caption ? "Stop tour" : "Tour"}
      </Button>
      {caption && (
        <>
          <div className="pointer-events-none fixed inset-x-0 top-0 z-30 h-14 bg-gradient-to-b from-black/60 to-transparent" />
          <div className="pointer-events-none fixed inset-x-0 bottom-0 z-30 h-40 bg-gradient-to-t from-black/70 to-transparent" />
          <div className="pointer-events-auto fixed inset-x-0 bottom-10 z-40 flex justify-center px-6">
            <div className="max-w-2xl rounded-[12px] bg-black/55 px-5 py-3 text-center text-white shadow-2xl backdrop-blur">
              <p className="text-[17px] leading-snug">{caption}</p>
              <div className="mt-2 flex items-center justify-center gap-3">
                <div className="flex gap-1">{Array.from({ length: count }, (_, i) => <span key={i} className={`h-1 w-5 rounded-full ${i <= step ? "bg-white" : "bg-white/30"}`} />)}</div>
                <button type="button" className="text-white/80 hover:text-white" onClick={() => { setMuted((m) => !m); window.speechSynthesis?.cancel(); }} aria-label={muted ? "Turn narration on" : "Mute narration"}>
                  {muted ? <VolumeX className="size-4" /> : <Volume2 className="size-4" />}
                </button>
                <button type="button" className="text-xs text-white/80 underline hover:text-white" onClick={stop}>Stop (Esc)</button>
              </div>
            </div>
          </div>
        </>
      )}
    </>
  );
}
