/** Your plan › Scenarios: every tested scenario as a card (icon, short headline, pass or fail, one
 * key number), click to watch it; the scenario library when the server has one; and the deeper
 * checks (more seeds, how sure, rewind, stress at scale) as tiles that open their panel. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Accessibility, Ambulance, ArrowUpDown, CircleCheck, CloudFog, CloudRainWind, DoorClosedLocked, UserPlus, Baby, Ban, Bomb, BookOpen, Boxes, Car, Check, CloudLightning, CloudRain, Code2, Dices, DoorClosed, Droplets, Fence, Flame, Footprints, Gauge, HeartPulse, History, Hourglass, Layers, Lock, Megaphone, Moon, Music, PartyPopper, Play, Repeat2, ShieldAlert, ShieldCheck, Siren, Snail, Sun, Swords, Thermometer, TriangleAlert, UsersRound, Waves, Wind, Zap, ZapOff } from "lucide-react";
import type * as React from "react";
import { useState } from "react";
import { api } from "@/api/client";
import { SWEEP_POLL_MS } from "@/api/poll";
import type { Attack } from "@/api/types";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/misc";
import { t } from "@/i18n";
import { fmtClock, fmtNum, fmtInt } from "@/lib/format";
import { cn } from "@/lib/utils";
import { ScriptCode } from "@/journey/ScriptCode";
import { SourceLink } from "@/journey/SourceLink";
import { type ScenarioKind, scenarioHeadline, scenarioKind, type StressCount } from "./gallery";
import type { Outcome, ScenarioRow } from "./scenarios";

const ICON: Record<ScenarioKind, React.ReactNode> = {
  block: <DoorClosed />, surge: <UsersRound />, slow: <Snail />, counter: <Repeat2 />, hold: <Hourglass />,
  script: <Code2 />, normal: <ShieldCheck />, other: <TriangleAlert />,
};

function OutcomeBadge({ outcome }: { outcome: Outcome }) {
  if (outcome === "break") return <Badge tone="danger">{t("work.breaks")}</Badge>;
  if (outcome === "holds") return <Badge tone="egress">{t("work.holds")}</Badge>;
  if (outcome === "running") return <Badge tone="neutral">{t("yourplan.sc_running")}</Badge>;
  if (outcome === "failed") return <Badge tone="caution">{t("yourplan.sc_failed")}</Badge>;
  return <Badge tone="neutral">{t(outcome === "preview" ? "work.preview" : "work.unknown")}</Badge>;
}

export function ScenarioCards({ rows, attacks, name, stress, onPlay, danger = 5 }: {
  rows: ScenarioRow[]; attacks: Attack[]; name: (id: string) => string; stress: Map<string, StressCount>; onPlay: (row: ScenarioRow) => void;
  /** the danger density (people per m²) from Settings */
  danger?: number;
}) {
  const shown = rows.filter((r) => r.kind === "baseline" || (r.kind === "attack" && !r.key.includes(":current:")));
  if (!shown.length) return <p className="text-sm text-muted">{t("yourplan.no_risks")}</p>;
  return (
    <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="scenario-gallery">
      {shown.map((r, i) => {
        const a = r.kind === "attack" ? attacks.find((x) => x.attack_id === r.attackId) : undefined;
        const kind = r.kind === "baseline" ? "normal" : scenarioKind(a);
        const playable = r.outcome !== "running" && r.outcome !== "failed";
        const kept = r.children.filter((c) => c.accepted).length;
        const st = r.attackId ? stress.get(r.attackId) : undefined;
        // the numbers are red only when the verdict is: a "Holds" badge never sits next to a red value
        const bad = r.outcome === "break";
        return (
          <li key={r.key} className="animate-deal-in" style={{ animationDelay: `${Math.min(i, 8) * 50}ms` }}>
            <div className="flex h-full flex-col gap-3 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm transition">
              <div className="flex items-start gap-3">
                <span className="grid size-11 shrink-0 place-items-center rounded-[12px] bg-surface-3 text-muted [&_svg]:size-5">{ICON[kind]}</span>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold leading-snug">{r.kind === "baseline" ? r.title : scenarioHeadline(a, name)}</p>
                  {a && <p className="line-clamp-1 text-xs text-muted" title={r.title}>{r.title}</p>}
                </div>
                <OutcomeBadge outcome={r.outcome} />
              </div>
              <dl className="grid grid-cols-2 gap-2 text-center">
                <div className="rounded-[8px] bg-surface-2 px-2 py-1.5">
                  <dt className="text-2xs text-muted">{t("plan.sc_out")}</dt>
                  {r.evacS == null && r.inside ? (
                    // the simulation stopped with people inside: say so instead of a blank
                    <dd className={cn("text-sm font-bold leading-7 tabular", bad && "text-danger")}>{t("plan.sc_left", { n: fmtInt(r.inside) })}</dd>
                  ) : r.evacS == null && playable && r.outcome !== "unknown" && r.outcome !== "preview" ? (
                    <dd className={cn("text-sm font-bold leading-7", bad && "text-danger")}>{t("plan.not_everyone_out")}</dd>
                  ) : <dd className="text-lg font-bold tabular">{r.evacS != null ? fmtClock(r.evacS) : "–"}</dd>}
                </div>
                <div className="rounded-[8px] bg-surface-2 px-2 py-1.5">
                  <dt className="text-2xs text-muted">{t("plan.sc_peak")}</dt>
                  <dd className={cn("text-lg font-bold tabular", bad && r.peak != null && r.peak >= danger && "text-danger")}>{r.peak != null ? fmtNum(r.peak, 1) : "–"}</dd>
                </div>
              </dl>
              <div className="flex flex-wrap gap-1.5 text-xs">
                {r.children.length > 0 && <Badge tone="outline">{t("plan.sc_fixes", { k: kept, n: r.children.length })}</Badge>}
                {st && <Badge tone={st.breaks ? "danger" : "egress"}>{t("plan.sc_stress", { k: st.breaks, n: st.runs })}</Badge>}
              </div>
              {a && <ScriptCode attack={a} />}
              <div className="mt-auto flex items-center justify-between gap-2">
                {a?.inspired_by?.source_url ? <SourceLink source={a.inspired_by} className="flex-1" /> : <span />}
                <button type="button" disabled={!playable} onClick={() => onPlay(r)} aria-label={t("plan.sc_watch", { title: r.title })}
                        className="inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-full bg-ink px-4 text-sm font-semibold text-plan transition hover:scale-[1.03] disabled:opacity-40">
                  <Play className="size-3.5" fill="currentColor" aria-hidden />{t("plan.sc_play")}
                </button>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

// --- the scenario catalogue (GET /scenarios?project_id=) and the sweep that runs it ----------------

let catalogueMissing = false;

/** One entry of the catalogue (novelty API): `icon` is a lucide icon name. */
interface CatalogueItem {
  id: string;
  title: string;
  description?: string;
  icon?: string;
  category?: string;
  category_label?: string;
  targets?: unknown[];
  applicable?: boolean;
}

interface SweepItem {
  key: string; label: string; run_id: string | null; status?: string; progress?: number | null; skipped?: string;
  title?: string; icon?: string; category?: string; targets?: unknown[];
  metrics?: { evac_time_p95_s: number | null; peak_density_ppm2: number; time_above_danger_s: number; agents_not_evacuated: number; agents_total: number };
}
interface Sweep { version: number | null; tier?: number; items: SweepItem[] }
interface Catalogue { items: CatalogueItem[]; defaults: string[] | null }

/** The icons the catalogue names (kebab-case or PascalCase), drawn from a fixed set so the
 * bundle doesn't carry every lucide icon; anything else gets the warning sign. */
const NAMED: Record<string, React.ReactNode> = {
  doorclosed: <DoorClosed />, users: <UsersRound />, usersround: <UsersRound />, snail: <Snail />, flame: <Flame />, firesxtinguisher: <Flame />,
  cloudrain: <CloudRain />, cloudlightning: <CloudLightning />, wind: <Wind />, siren: <Siren />, repeat: <Repeat2 />, repeat2: <Repeat2 />,
  hourglass: <Hourglass />, timer: <Hourglass />, shieldalert: <ShieldAlert />, trianglealert: <TriangleAlert />, alerttriangle: <TriangleAlert />,
  footprints: <Footprints />, accessibility: <Accessibility />, heartpulse: <HeartPulse />, megaphone: <Megaphone />, lock: <Lock />,
  fence: <Fence />, ambulance: <Ambulance />, zap: <Zap />, zapoff: <ZapOff />, lightbulboff: <ZapOff />, moon: <Moon />, sun: <Sun />,
  thermometer: <Thermometer />, droplets: <Droplets />, waves: <Waves />, ban: <Ban />, arrowleftright: <Repeat2 />, code: <Code2 />, code2: <Code2 />,
  arrowupdown: <ArrowUpDown />, cloudfog: <CloudFog />, layers: <Layers />, circlecheck: <CircleCheck />, userplus: <UserPlus />, doorclosedlocked: <DoorClosedLocked />, cloudrainwind: <CloudRainWind />,
  swords: <Swords />, baby: <Baby />, car: <Car />, bomb: <Bomb />, music: <Music />, partypopper: <PartyPopper />,
};
const namedIcon = (name: string | null | undefined): React.ReactNode =>
  NAMED[(name ?? "").toLowerCase().replace(/[^a-z0-9]/g, "")] ?? <TriangleAlert />;

const busy = (it: SweepItem) => it.status === "running" || it.status === "queued";

function useCatalogue(projectId: string) {
  return useQuery({
    queryKey: ["scenario-catalogue", projectId],
    enabled: !catalogueMissing,
    retry: false,
    staleTime: 60_000,
    queryFn: async (): Promise<Catalogue | null> => {
      try {
        const out = await api.get<CatalogueItem[] | { scenarios?: CatalogueItem[]; not_applicable?: { id: string; title: string; reason?: string }[]; default_sweep?: string[] }>(
          `/scenarios?project_id=${encodeURIComponent(projectId)}`);
        if (Array.isArray(out)) return { items: out, defaults: null };
        const off = (out.not_applicable ?? []).map((x) => ({ id: x.id, title: x.title, description: x.reason, applicable: false } as CatalogueItem));
        return { items: [...(out.scenarios ?? []), ...off], defaults: out.default_sweep ?? null };
      } catch (e) {
        if ((e as { status?: number }).status === 404) catalogueMissing = true;
        return null;
      }
    },
  });
}

/** Pick scenarios from the catalogue (or the six standard what-ifs on a server without one), run
 * them in parallel sandboxes, and watch any result in the replay. */
export function ScenarioCatalogue({ projectId, version, onPlay, danger = 5 }: {
  projectId: string; version: number; onPlay: (runId: string, title: string) => void; danger?: number;
}) {
  const qc = useQueryClient();
  const catalogue = useCatalogue(projectId);
  const items = catalogue.data?.items ?? [];
  const defaults = catalogue.data?.defaults;
  const sweep = useQuery({
    queryKey: ["sweep", projectId],
    queryFn: () => api.get<Sweep>(`/projects/${projectId}/sweep`),
    refetchInterval: (q) => (q.state.data?.items.some(busy) ? SWEEP_POLL_MS : false),
  });
  const [chosen, setChosen] = useState<Set<string> | null>(null);
  const picks = chosen ?? new Set(defaults ?? items.filter((i) => i.applicable !== false).slice(0, 6).map((i) => i.id));
  const run = useMutation({
    mutationFn: () => api.post<Sweep>(`/projects/${projectId}/sweep`, items.length ? { scenarios: [...picks] } : {}),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["sweep", projectId] }); toast.success(t("plan.sweep_queued")); },
    onError: (e) => toast.error(e.message, { description: (e as { hint?: string | null }).hint ?? undefined }),
  });
  const results = sweep.data?.items ?? [];
  const running = results.some(busy) || run.isPending;
  const stale = sweep.data?.version != null && sweep.data.version !== version;
  const groups = [...new Set(items.map((i) => i.category_label ?? i.category ?? ""))];
  const flip = (id: string) => { const next = new Set(picks); if (next.has(id)) next.delete(id); else next.add(id); setChosen(next); };

  return (
    <section aria-labelledby="cat-h" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="cat-h" className="flex items-center gap-2 text-lg font-semibold"><BookOpen className="size-5 text-signal" aria-hidden />{t(items.length ? "plan.library" : "plan.whatifs")}</h2>
          <p className="text-sm text-muted">{t(items.length ? "plan.library_lead" : "plan.whatifs_lead")}</p>
        </div>
        <Button variant={results.length ? "secondary" : "primary"} disabled={running || (items.length > 0 && picks.size === 0)} onClick={() => run.mutate()}>
          {running ? <Spinner /> : <Boxes />}{items.length ? t("plan.sweep_run", { n: picks.size }) : t("plan.whatifs_run")}
        </Button>
      </div>

      {groups.map((g) => (
        <div key={g || "all"} className="space-y-2">
          {g && <h3 className="text-sm font-semibold text-muted">{g}</h3>}
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {items.filter((i) => (i.category_label ?? i.category ?? "") === g).map((it) => {
              const off = it.applicable === false;
              const on = picks.has(it.id) && !off;
              return (
                <li key={it.id}>
                  <label className={cn("flex h-full cursor-pointer items-start gap-3 rounded-[var(--radius-panel)] border-2 bg-surface p-3 shadow-sm transition",
                                       on ? "border-signal" : "border-transparent hover:border-border-strong", off && "cursor-not-allowed opacity-55")}>
                    <input type="checkbox" className="sr-only" checked={on} disabled={off} onChange={() => flip(it.id)} aria-label={it.title} />
                    <span className={cn("grid size-10 shrink-0 place-items-center rounded-[10px] [&_svg]:size-5", on ? "bg-signal text-signal-ink" : "bg-surface-3 text-muted")} aria-hidden>{namedIcon(it.icon)}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block font-semibold leading-snug">{it.title}</span>
                      {it.description && <span className="line-clamp-2 block text-xs text-muted">{it.description}</span>}
                      {off ? <span className="mt-1 block text-2xs font-medium text-muted">{t("plan.not_applicable")}</span>
                        : (it.targets?.length ?? 0) > 0 && (
                          <span className="mt-1.5 flex flex-wrap gap-1">
                            {it.targets!.filter((x): x is string => typeof x === "string").slice(0, 3).map((x) => (
                              <span key={x} className="line-clamp-2 max-w-full rounded-[6px] bg-surface-3 px-1.5 py-0.5 text-2xs text-ink" title={x}>{x}</span>
                            ))}
                          </span>
                        )}
                    </span>
                    {on && <Check className="size-4 shrink-0 text-signal" aria-hidden />}
                  </label>
                </li>
              );
            })}
          </ul>
        </div>
      ))}

      {results.length > 0 && (
        <div className="space-y-2">
          <h3 className="flex flex-wrap items-center gap-2 text-sm font-semibold">{t("plan.sweep_results")}{stale && <Badge tone="caution">{t("plan.sweep_stale")}</Badge>}</h3>
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {results.map((it) => {
              const m = it.metrics;
              const bad = !!m && (m.peak_density_ppm2 >= danger || m.agents_not_evacuated > 0);
              const title = it.title ?? it.label;
              return (
                <li key={it.key} className="flex items-center gap-3 rounded-[var(--radius-panel)] border border-border bg-surface p-3 shadow-sm">
                  <span className="grid size-10 shrink-0 place-items-center rounded-[10px] bg-surface-3 text-muted [&_svg]:size-5" aria-hidden>
                    {it.icon ? namedIcon(it.icon) : <Boxes />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-start justify-between gap-2">
                      <span className="line-clamp-2 block text-sm font-semibold leading-snug">{title}</span>
                      {m && <Badge tone={bad ? "danger" : "egress"}>{bad ? t("work.breaks") : t("work.holds")}</Badge>}
                    </span>
                    {it.skipped ? <span className="block text-2xs text-muted">{it.skipped}</span> : !m ? (
                      <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-surface-3"><span className="block h-full animate-pulse rounded-full bg-signal" style={{ width: `${Math.max(8, (it.progress ?? 0) * 100)}%` }} /></span>
                    ) : (
                      <span className="block text-xs text-muted tabular">{t("yourplan.sc_metrics", { evac: m.evac_time_p95_s != null ? fmtClock(m.evac_time_p95_s) : t("rewind.not_out"), peak: fmtNum(m.peak_density_ppm2, 1) })}</span>
                    )}
                  </span>
                  {m && it.run_id && (
                    <button type="button" onClick={() => onPlay(it.run_id!, title)} aria-label={t("plan.sc_watch", { title })}
                            className="grid size-11 shrink-0 place-items-center rounded-full bg-ink text-plan transition hover:scale-105">
                      <Play className="size-4" fill="currentColor" aria-hidden />
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </section>
  );
}

// --- deeper checks ----------------------------------------------------------------------------

type CheckKey = "seeds" | "range" | "rewind" | "stress";

const CHECK_ICON: Record<CheckKey, React.ReactNode> = { seeds: <Dices />, range: <Gauge />, rewind: <History />, stress: <Layers /> };

export function DeeperChecks({ status, panels }: { status: Record<CheckKey, string>; panels: Partial<Record<CheckKey, React.ReactNode>> }) {
  const [open, setOpen] = useState<CheckKey | null>(null);
  const keys = (["rewind", "stress", "seeds", "range"] as const).filter((k) => panels[k] !== undefined);
  return (
    <section aria-labelledby="deeper-h" className="space-y-3">
      <h2 id="deeper-h" className="text-lg font-semibold">{t("plan.deeper")}</h2>
      <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {keys.map((k) => (
          <li key={k}>
            <button type="button" aria-expanded={open === k} onClick={() => setOpen(open === k ? null : k)}
                    className={cn("flex h-full min-h-20 w-full items-center gap-3 rounded-[var(--radius-panel)] border-2 bg-surface p-3 text-left shadow-sm transition hover:-translate-y-0.5",
                                  open === k ? "border-signal" : "border-transparent hover:border-border-strong")}>
              <span className="grid size-10 shrink-0 place-items-center rounded-full bg-signal-soft text-signal [&_svg]:size-5">{CHECK_ICON[k]}</span>
              <span className="min-w-0">
                <span className="block font-semibold leading-tight">{t(`plan.check_${k}`)}</span>
                <span className="block text-xs text-muted">{status[k]}</span>
              </span>
            </button>
          </li>
        ))}
      </ul>
      {open && <div className="animate-deal-in">{panels[open]}</div>}
    </section>
  );
}
