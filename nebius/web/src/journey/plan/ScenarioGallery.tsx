/** Your plan › Scenarios: every tested scenario as a card (icon, short headline, pass or fail, one
 * key number), click to watch it; the scenario library when the server has one; and the deeper
 * checks (more seeds, how sure, rewind, stress at scale) as tiles that open their panel. */
import { useQuery } from "@tanstack/react-query";
import { BookOpen, Code2, Dices, DoorClosed, ExternalLink, Gauge, History, Hourglass, Layers, Play, Repeat2, ShieldCheck, Snail, TriangleAlert, UsersRound } from "lucide-react";
import type * as React from "react";
import { useState } from "react";
import { api } from "@/api/client";
import type { Attack } from "@/api/types";
import { Badge } from "@/components/ui/badge";
import { t } from "@/i18n";
import { fmtClock, fmtNum } from "@/lib/format";
import { cn } from "@/lib/utils";
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

export function ScenarioCards({ rows, attacks, name, stress, onPlay }: {
  rows: ScenarioRow[]; attacks: Attack[]; name: (id: string) => string; stress: Map<string, StressCount>; onPlay: (row: ScenarioRow) => void;
}) {
  const shown = rows.filter((r) => r.kind === "baseline" || (r.kind === "attack" && !r.key.includes(":current:")));
  if (!shown.length) return <p className="text-sm text-muted">{t("yourplan.no_risks")}</p>;
  return (
    <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" data-testid="scenario-gallery">
      {shown.map((r, i) => {
        const a = r.kind === "attack" ? attacks.find((x) => x.attack_id === r.attackId) : undefined;
        const kind = r.kind === "baseline" ? "normal" : scenarioKind(a);
        const playable = r.outcome !== "running" && r.outcome !== "failed";
        const kept = r.children.filter((c) => c.accepted).length;
        const st = r.attackId ? stress.get(r.attackId) : undefined;
        const bad = r.outcome === "break";
        return (
          <li key={r.key} className="animate-deal-in" style={{ animationDelay: `${Math.min(i, 8) * 50}ms` }}>
            <div className={cn("flex h-full flex-col gap-3 rounded-[var(--radius-panel)] border-2 bg-surface p-4 shadow-sm transition",
                               bad ? "border-danger/35" : r.outcome === "holds" ? "border-egress/30" : "border-border")}>
              <div className="flex items-start gap-3">
                <span className={cn("grid size-11 shrink-0 place-items-center rounded-[12px] [&_svg]:size-5",
                                    bad ? "bg-danger-soft text-danger-strong" : r.outcome === "holds" ? "bg-egress-soft text-egress-strong" : "bg-surface-3 text-muted")}>{ICON[kind]}</span>
                <div className="min-w-0 flex-1">
                  <p className="font-semibold leading-snug">{r.kind === "baseline" ? r.title : scenarioHeadline(a, name)}</p>
                  {a && <p className="line-clamp-1 text-xs text-muted" title={r.title}>{r.title}</p>}
                </div>
                <OutcomeBadge outcome={r.outcome} />
              </div>
              <dl className="grid grid-cols-2 gap-2 text-center">
                <div className="rounded-[8px] bg-surface-2 px-2 py-1.5">
                  <dt className="text-2xs text-muted">{t("plan.sc_out")}</dt>
                  <dd className="text-lg font-bold tabular">{r.evacS != null ? fmtClock(r.evacS) : "–"}</dd>
                </div>
                <div className="rounded-[8px] bg-surface-2 px-2 py-1.5">
                  <dt className="text-2xs text-muted">{t("plan.sc_peak")}</dt>
                  <dd className={cn("text-lg font-bold tabular", r.peak != null && r.peak >= 5 && "text-danger")}>{r.peak != null ? fmtNum(r.peak, 1) : "–"}</dd>
                </div>
              </dl>
              <div className="flex flex-wrap gap-1.5 text-xs">
                {r.children.length > 0 && <Badge tone="outline">{t("plan.sc_fixes", { k: kept, n: r.children.length })}</Badge>}
                {st && <Badge tone={st.breaks ? "danger" : "egress"}>{t("plan.sc_stress", { k: st.breaks, n: st.runs })}</Badge>}
              </div>
              <div className="mt-auto flex flex-wrap items-center justify-between gap-2">
                {a?.inspired_by?.source_url ? (
                  <a href={a.inspired_by.source_url} target="_blank" rel="noreferrer" className="flex min-h-11 min-w-0 items-center gap-1 text-xs text-signal hover:underline">
                    <ExternalLink className="size-3 shrink-0" /><span className="truncate">{a.inspired_by.incident}{a.inspired_by.year ? ` (${a.inspired_by.year})` : ""}</span>
                  </a>
                ) : <span />}
                <button type="button" disabled={!playable} onClick={() => onPlay(r)} aria-label={t("plan.sc_watch", { title: r.title })}
                        className="inline-flex min-h-11 items-center gap-1.5 rounded-full bg-ink px-4 text-sm font-semibold text-plan transition hover:scale-[1.03] disabled:opacity-40">
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

// --- the scenario library (GET /scenarios?project_id=): shown only when the server has it --------

let libraryMissing = false;

interface LibraryItem { id?: string; scenario_id?: string; title?: string; name?: string; kind?: string; category?: string; description?: string; summary?: string }

export function ScenarioLibrary({ projectId }: { projectId: string }) {
  const q = useQuery({
    queryKey: ["scenario-library", projectId],
    enabled: !libraryMissing,
    retry: false,
    staleTime: 60_000,
    queryFn: async () => {
      try {
        const out = await api.get<LibraryItem[] | { items?: LibraryItem[]; scenarios?: LibraryItem[] }>(`/scenarios?project_id=${encodeURIComponent(projectId)}`);
        return Array.isArray(out) ? out : out.items ?? out.scenarios ?? [];
      } catch (e) {
        if ((e as { status?: number }).status === 404) libraryMissing = true;
        return null;
      }
    },
  });
  const items = q.data ?? [];
  if (!items.length) return null;
  return (
    <section aria-labelledby="lib-h" className="space-y-3">
      <h2 id="lib-h" className="flex items-center gap-2 text-lg font-semibold"><BookOpen className="size-5 text-signal" aria-hidden />{t("plan.library")}</h2>
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {items.slice(0, 24).map((it, i) => (
          <li key={it.id ?? it.scenario_id ?? i} className="rounded-[var(--radius-panel)] border border-border bg-surface p-3 shadow-sm">
            <p className="font-semibold leading-snug">{it.title ?? it.name ?? it.id}</p>
            {(it.kind ?? it.category) && <Badge tone="outline" className="mt-1">{it.kind ?? it.category}</Badge>}
            {(it.summary ?? it.description) && <p className="mt-1 line-clamp-2 text-xs text-muted">{it.summary ?? it.description}</p>}
          </li>
        ))}
      </ul>
    </section>
  );
}

// --- deeper checks ----------------------------------------------------------------------------

export type CheckKey = "seeds" | "range" | "rewind" | "stress";

const CHECK_ICON: Record<CheckKey, React.ReactNode> = { seeds: <Dices />, range: <Gauge />, rewind: <History />, stress: <Layers /> };

export function DeeperChecks({ status, panels }: { status: Record<CheckKey, string>; panels: Record<CheckKey, React.ReactNode> }) {
  const [open, setOpen] = useState<CheckKey | null>(null);
  const keys: CheckKey[] = ["rewind", "stress", "seeds", "range"];
  return (
    <section aria-labelledby="deeper-h" className="space-y-3">
      <h2 id="deeper-h" className="text-lg font-semibold">{t("plan.deeper")}</h2>
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
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
