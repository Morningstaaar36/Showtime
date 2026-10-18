/** Your plan › Floors (multi-storey): one small plan per storey, top floor first, with how many
 * people start there, when it is clear, its emptying curve and how many people took each stair.
 * Click a floor to watch it in the replay. */
import { Footprints, Play, Timer, Users } from "lucide-react";
import { useMemo } from "react";
import type { Pt, Venue } from "@/api/types";
import { t } from "@/i18n";
import { fmtClock, fmtInt } from "@/lib/format";
import { floorNamer } from "@/panels/FloorMenu";
import type { Trajectory } from "@/replay/trajectory";
import { floorsBottomUp, venueBounds } from "@/scene/geom";
import { FloorChart } from "./ScenarioViewer";
import { floorsSummary } from "./floors";
import { Sparkline } from "./visuals";

const path = (pts: Pt[], close = true) => pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(2)},${(-p[1]).toFixed(2)}`).join("") + (close ? "Z" : "");

function MiniPlan({ venue, floorId, stairUse, bounds }: { venue: Venue; floorId: string; stairUse: Record<string, number>; bounds: [number, number, number, number] }) {
  const f = venue.floors.find((x) => x.floor_id === floorId)!;
  const [x0, y0, x1, y1] = bounds;
  const w = Math.max(x1 - x0, 1), h = Math.max(y1 - y0, 1);
  const pad = Math.max(w, h) * 0.04;
  const stairs = (venue.stairs ?? []).filter((s) => s.from_floor === floorId || s.to_floor === floorId);
  const sw = Math.max(w, h) / 220;
  return (
    <svg viewBox={`${x0 - pad} ${-y1 - pad} ${w + 2 * pad} ${h + 2 * pad}`} className="h-32 w-full" aria-hidden>
      <path d={path(f.walkable as Pt[])} fill="var(--surface-2)" stroke="var(--ink)" strokeWidth={sw * 2} strokeLinejoin="round" />
      {f.obstacles.filter((o) => o.kind === "wall").map((o) => (
        <path key={o.id} d={o.line && o.line.length >= 2 ? path(o.line as Pt[], false) : path(o.polygon as Pt[])} fill="none" stroke="var(--line)" strokeWidth={sw} />
      ))}
      {f.zones.map((z) => <path key={z.id} d={path(z.polygon as Pt[])} fill="var(--signal)" fillOpacity={0.12} stroke="none" />)}
      {stairs.map((s) => {
        const poly = (s.from_floor === floorId ? s.top_polygon : s.bottom_polygon) as Pt[];
        return <path key={s.id} d={path(poly)} fill="var(--sky)" fillOpacity={0.85} stroke="var(--sky-strong)" strokeWidth={sw} />;
      })}
      {f.exits.map((e) => <path key={e.id} d={path(e.polygon as Pt[])} fill="var(--egress)" stroke="var(--egress)" strokeWidth={sw * 3} />)}
      {stairs.map((s) => {
        const poly = (s.from_floor === floorId ? s.top_polygon : s.bottom_polygon) as Pt[];
        const cx = poly.reduce((a, p) => a + p[0], 0) / poly.length, cy = poly.reduce((a, p) => a + p[1], 0) / poly.length;
        return (
          <text key={`n${s.id}`} x={cx} y={-cy - Math.max(w, h) * 0.035} textAnchor="middle" fontSize={Math.max(w, h) * 0.06}
                className="fill-ink font-semibold" style={{ paintOrder: "stroke", stroke: "var(--surface)", strokeWidth: Math.max(w, h) * 0.012 }}>
            {fmtInt(stairUse[s.id] ?? 0)}
          </text>
        );
      })}
    </svg>
  );
}

export function FloorsTab({ venue, traj, onWatch }: { venue: Venue; traj: Trajectory | null; onWatch: (floorId: string) => void }) {
  const name = useMemo(() => floorNamer(venue), [venue]);
  const summary = useMemo(() => (traj ? floorsSummary(traj, venue) : null), [traj, venue]);
  const bounds = useMemo(() => venueBounds(venue), [venue]);
  const floors = floorsBottomUp(venue).reverse();
  const totalStair = summary ? Object.values(summary.stairs).reduce((a, b) => a + b, 0) : 0;
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm text-muted">
        <span className="flex items-center gap-1.5"><span className="size-3 rounded-[2px] bg-egress" />{t("plan.fl_exit")}</span>
        <span className="flex items-center gap-1.5"><span className="size-3 rounded-[2px] bg-sky" />{t("plan.fl_stair")}</span>
        <span className="flex items-center gap-1.5"><span className="size-3 rounded-[2px] bg-signal/20" />{t("plan.fl_crowd")}</span>
        {summary && <span className="flex items-center gap-1.5 font-medium text-ink"><Footprints className="size-4" />{t("plan.fl_stair_total", { n: fmtInt(totalStair) })}</span>}
      </div>
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="floor-cards">
        {floors.map((f) => {
          const st = summary?.floors.find((x) => x.floorId === f.floor_id);
          const people = f.zones.reduce((n, z) => n + z.people, 0);
          return (
            <li key={f.floor_id}>
              <button type="button" onClick={() => onWatch(f.floor_id)} aria-label={t("plan.fl_watch", { floor: name(f.floor_id) })}
                      className="group flex h-full w-full flex-col gap-2 rounded-[var(--radius-panel)] border-2 border-transparent bg-surface p-3 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-signal">
                <span className="flex items-center justify-between gap-2">
                  <span className="font-semibold">{name(f.floor_id)}</span>
                  <Play className="size-4 text-muted group-hover:text-signal" aria-hidden />
                </span>
                <MiniPlan venue={venue} floorId={f.floor_id} stairUse={summary?.stairs ?? {}} bounds={bounds} />
                <span className="grid grid-cols-2 gap-2 text-sm">
                  <span className="rounded-[8px] bg-surface-2 px-2 py-1">
                    <span className="flex items-center gap-1 text-2xs text-muted"><Users className="size-3" />{t("plan.fl_start")}</span>
                    <span className="block text-lg font-bold tabular">{fmtInt(st?.start ?? people)}</span>
                  </span>
                  <span className="rounded-[8px] bg-surface-2 px-2 py-1">
                    <span className="flex items-center gap-1 text-2xs text-muted"><Timer className="size-3" />{t("plan.fl_clear")}</span>
                    <span className="block text-lg font-bold tabular">{st ? (st.clearS != null ? fmtClock(st.clearS) : st.start ? t("plan.fl_never") : "–") : "–"}</span>
                  </span>
                </span>
                {st && st.series.length > 1 && <Sparkline values={st.series} tone="var(--sky)" label={t("plan.fl_curve", { floor: name(f.floor_id) })} />}
              </button>
            </li>
          );
        })}
      </ul>
      {traj && <FloorChart traj={traj} floorName={name} />}
    </div>
  );
}
