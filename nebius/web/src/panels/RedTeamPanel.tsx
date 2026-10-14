import * as Tabs from "@radix-ui/react-tabs";
import { Activity, ArrowRight, Bot, Check, Columns2, ExternalLink, Eye, GitBranch, History, Settings2, ShieldAlert, ShieldCheck, Square, Swords, Wrench, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { qk, useApplySession, useSession, useSessions, useStartRun, useStartSession, useStopSession } from "@/api/queries";
import type { ProjectDetail } from "@/api/types";
import { type SessionView, type TreeNode, useSessionStream } from "@/api/useSessionStream";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { PanelTitle, Progress, Spinner } from "@/components/ui/misc";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { EmptyState } from "@/components/ui/states";
import { t } from "@/i18n";
import { ScriptCode } from "@/journey/ScriptCode";
import { fmtDuration, fmtInt, fmtMoney, fmtNum, fmtTokens } from "@/lib/format";
import { cn } from "@/lib/utils";
import { usePlayback } from "@/state/playback";
import { useUi } from "@/state/ui";
import { BranchTree } from "./BranchTree";
import { describeEvent, describeOp } from "./describe";
import { exitLabeler, textHumanizer } from "./Inspector";

const PHASES = ["baseline", "red_team", "screening", "simulating", "blue_team", "confirming", "judging", "done"];

export function useRedTeamSession(projectId: string) {
  const sessions = useSessions(projectId);
  const [picked, setPicked] = useState<string | null>(null);
  const sessionId = picked ?? sessions.data?.[0]?.id ?? null;
  return { sessionId, setPicked, sessions };
}

/** Right-hand panel in Red Team mode. */
export function RedTeamPanel({ project, sessionId, onPickSession }: {
  project: ProjectDetail; sessionId: string | null; onPickSession: (id: string) => void;
}) {
  const venue = project.version.venue;
  const label = useMemo(() => exitLabeler(venue), [venue]);
  const human = useMemo(() => textHumanizer(venue), [venue]);
  const session = useSession(sessionId);
  const view = useSessionStream(sessionId);
  const start = useStartSession();
  const stop = useStopSession();
  const apply = useApplySession(project.id);
  const setActive = useUi((s) => s.setActiveRun);
  const activeRun = useUi((s) => s.activeRunId);
  const [cfg, setCfg] = useState({ max_rounds: 2, attacks_per_round: 3, fixes_per_attack: 2 });
  const running = view.status === "running" || session.data?.status === "running";
  const finished = !!session.data && (session.data.status === "finished" || session.data.status === "stopped") && view.ended;

  // refresh the session list (top-bar cost meter, history) once the stream ends
  const qc = useQueryClient();
  useEffect(() => {
    if (!view.ended || !sessionId) return;
    void qc.invalidateQueries({ queryKey: qk.sessions(project.id) });
    void qc.invalidateQueries({ queryKey: qk.session(sessionId) });
  }, [view.ended, sessionId, project.id, qc]);

  // show the newest finished run in 3D while the session is live
  useEffect(() => {
    const done = Object.values(view.nodes).filter((n) => n.status !== "running" && n.status !== "pending");
    if (running && done.length) setActive(done[done.length - 1].run_id);
  }, [view.lastSeq]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (view.ended) void session.refetch();
  }, [view.ended]); // eslint-disable-line react-hooks/exhaustive-deps
  // when a finished session opens, show the confirmed fixed plan (or the baseline)
  const summaryRun = (session.data?.summary as Record<string, unknown> | null | undefined)?.final_run_id
    ?? (session.data?.summary as Record<string, unknown> | null | undefined)?.baseline_run_id;
  useEffect(() => {
    if (!running && typeof summaryRun === "string" && !useUi.getState().activeRunId) setActive(summaryRun);
  }, [summaryRun, running]); // eslint-disable-line react-hooks/exhaustive-deps

  const pick = (n: TreeNode) => setActive(n.run_id);
  const phaseIdx = Math.max(0, PHASES.indexOf(view.phase));

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-semibold tracking-tight"><Swords className="size-5 text-danger" />{t("redteam.title")}</h2>
          <p className="mt-1 text-sm text-muted">{t("redteam.lead")}</p>
        </div>
      </div>

      <div className="flex gap-2">
        {!running ? (
          <Button variant="primary" size="lg" className="flex-1" disabled={start.isPending || !project.validation.ok}
                  onClick={() => start.mutate({ project_id: project.id, config: cfg }, {
                    onSuccess: (s) => { onPickSession(s.id); toast(t("redteam.title") + " started"); },
                    onError: (e) => toast.error(e.message, { description: (e as { hint?: string }).hint }),
                  })}>
            <Swords />{t("redteam.start")}
          </Button>
        ) : (
          <Button size="lg" className="flex-1" onClick={() => sessionId && stop.mutate(sessionId)}><Square className="size-3.5" />{t("redteam.stop")}</Button>
        )}
        <Popover>
          <PopoverTrigger asChild><Button size="lg" variant="secondary" aria-label="Session settings"><Settings2 /></Button></PopoverTrigger>
          <PopoverContent align="end" className="w-64 space-y-3">
            <p className="font-semibold">{t("redteam.budget")}</p>
            {([["max_rounds", t("redteam.rounds"), 1, 4], ["attacks_per_round", t("redteam.attacks"), 1, 6], ["fixes_per_attack", t("redteam.fixes"), 1, 4]] as const).map(([k, l, lo, hi]) => (
              <div key={k} className="flex items-center justify-between gap-3">
                <Label htmlFor={k} className="text-sm font-normal">{l}</Label>
                <Input id={k} type="number" min={lo} max={hi} value={cfg[k]} className="h-8 w-20"
                       onChange={(e) => setCfg((c) => ({ ...c, [k]: Math.min(hi, Math.max(lo, Number(e.target.value) || lo)) }))} />
              </div>
            ))}
            <p className="text-xs text-muted">More rounds find more weaknesses but take longer. Each attack and fix is a real simulation.</p>
          </PopoverContent>
        </Popover>
      </div>

      {!sessionId && <EmptyState icon={<Swords />} title={t("redteam.empty")} body="Attack cards cite the real incident that inspired them. Fixes are kept only when the simulation shows they help." />}

      {sessionId && (
        <>
          {(running || view.phase) && !finished && (
            <section aria-live="polite" className="rounded-[var(--radius-panel)] border border-border bg-surface-2 p-3">
              <div className="flex items-center gap-2 text-sm font-medium">
                {running && <Spinner className="text-signal" />}
                {t(`redteam.phase_${view.phase || "baseline"}`)}{view.round > 0 && ` · ${t("redteam.round", { n: view.round })}`}
              </div>
              <Progress className="mt-2" value={(phaseIdx / (PHASES.length - 1)) * 100} />
              {view.message && <p className="mt-1.5 truncate text-xs text-muted">{view.message}</p>}
            </section>
          )}
          <Scoreboard view={view} />
          {finished && session.data?.summary && (
            <FinalCard view={view} summary={session.data.summary as Record<string, unknown>} human={human}
                       onApply={() => sessionId && apply.mutate(sessionId, {
                         onSuccess: (r) => toast.success(t("redteam.plan_applied", { n: r.version.version })),
                         onError: (e) => toast.error(e.message),
                       })} applying={apply.isPending} onShow={(id) => setActive(id)} />
          )}
          <Tabs.Root defaultValue="cards">
            <Tabs.List className="flex gap-0.5 rounded-full bg-surface-2 p-1">
              {[["cards", <Swords key="s" />, "Attacks and fixes"], ["tree", <GitBranch key="g" />, t("redteam.branch_tree")], ["activity", <Activity key="a" />, t("redteam.activity")]].map(([v, icon, l]) => (
                <Tabs.Trigger key={v as string} value={v as string}
                              className="flex flex-1 items-center justify-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1.5 text-sm text-muted hover:text-ink data-[state=active]:bg-surface data-[state=active]:font-medium data-[state=active]:text-ink data-[state=active]:shadow-sm [&_svg]:size-3.5">
                  {icon}{l}
                </Tabs.Trigger>
              ))}
            </Tabs.List>
            <Tabs.Content value="cards" className="mt-3 space-y-3">
              {view.attacks.length === 0 && <p className="text-sm text-muted">{running ? "The red team is reading the plan and similar real incidents…" : "No attacks yet."}</p>}
              {view.attacks.map(({ attack, round }, i) => (
                <AttackCard key={attack.attack_id} index={i} attack={attack} round={round} view={view} label={label} human={human}
                            active={activeRun} onShow={(id) => setActive(id)} projectId={project.id} />
              ))}
            </Tabs.Content>
            <Tabs.Content value="tree" className="mt-3">
              <BranchTree nodes={view.nodes} activeRunId={activeRun} onPick={pick} human={human} />
              <p className="mt-2 text-xs text-muted">Click a branch to replay that simulation in 3D.</p>
            </Tabs.Content>
            <Tabs.Content value="activity" className="mt-3">
              <ActivityFeed view={view} />
            </Tabs.Content>
          </Tabs.Root>
          {view.cost && (
            <p className="text-xs text-muted tabular">
              AI usage: {fmtTokens(view.cost.tokens_total)} of {fmtTokens(view.cost.budget_tokens)} tokens · {fmtMoney(view.cost.cost_usd)}
            </p>
          )}
        </>
      )}
      <p className="text-xs text-muted">{t("app.disclaimer")}</p>
    </div>
  );
}

function Scoreboard({ view }: { view: SessionView }) {
  if (!view.scoreboard.length) return null;
  return (
    <section aria-label={t("redteam.scoreboard")} className="rounded-[var(--radius-panel)] border border-border p-3">
      <PanelTitle>{t("redteam.scoreboard")}</PanelTitle>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {view.scoreboard.map((r, i) => (
          <span key={r.round} className="flex items-center gap-2">
            {i > 0 && <ArrowRight className="size-4 text-line" />}
            <span className="text-center">
              <span className={cn("block text-2xl font-semibold leading-none tabular", r.breaks ? "text-danger" : "text-egress")}>{r.breaks}</span>
              <span className="text-2xs text-muted">round {r.round} · {r.attacks} attacks</span>
            </span>
          </span>
        ))}
        <span className="ml-auto text-right">
          <span className="block text-2xl font-semibold leading-none text-egress tabular">{view.fixesAccepted}</span>
          <span className="text-2xs text-muted">fixes kept</span>
        </span>
      </div>
      <p className="mt-2 text-xs text-muted">Breaks per round. The red team attacks the improved plan in each new round.</p>
    </section>
  );
}

function TimeTravel({ projectId, attack, fix, attackRunId, active }: {
  projectId: string; attack: SessionView["attacks"][number]["attack"]; fix: SessionView["fixes"][number]["fix"];
  attackRunId: string; active: string | null;
}) {
  const start = useStartRun();
  const setActive = useUi((s) => s.setActiveRun);
  const [t, setT] = useState(0);
  useEffect(() => {
    if (active !== attackRunId) return;
    const id = window.setInterval(() => setT(Math.round(usePlayback.getState().t)), 500);
    return () => window.clearInterval(id);
  }, [active, attackRunId]);
  if (active !== attackRunId || t < 5) return null;
  return (
    <Button size="sm" variant="ghost" className="h-7" disabled={start.isPending}
            title="Re-run this attack with the fix starting at the current replay time"
            onClick={() => start.mutate({ project_id: projectId, tier: 2, attack, fix, intervention_at_s: t,
                                          parent_run_id: attackRunId, label: `${fix.fix_id} from ${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}` }, {
              onSuccess: (r) => { setActive(r.id); toast(`Time travel: ${fix.title} from ${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`); },
              onError: (e) => toast.error(e.message),
            })}>
      <History />Apply from {Math.floor(t / 60)}:{String(t % 60).padStart(2, "0")}
    </Button>
  );
}

function AttackCard({ attack, round, view, label, human, index, active, onShow, projectId }: {
  attack: SessionView["attacks"][number]["attack"]; round: number; view: SessionView; label: (id: string) => string;
  human: (text: string) => string;
  index: number; active: string | null; onShow: (runId: string) => void; projectId: string;
}) {
  const node = view.nodes[`atk:${attack.attack_id}`];
  const run = node ? view.runs[node.run_id] : undefined;
  const fixes = view.fixes.filter((f) => f.attack_id === attack.attack_id);
  const status = run ? (run.is_break ? "break" : "holds") : node?.status === "running" ? "running" : "waiting";
  const src = attack.inspired_by;
  return (
    <article className={cn("animate-deal-in overflow-hidden rounded-[var(--radius-panel)] border bg-surface",
      status === "break" ? "border-danger/40" : "border-border", node && active === node.run_id && "ring-2 ring-signal")}
             style={{ animationDelay: `${(index % 5) * 90}ms` }}>
      <div className={cn("h-1", status === "break" ? "bg-danger" : status === "holds" ? "bg-egress" : "bg-surface-3")} />
      <div className="space-y-2 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-2xs font-medium text-muted">{attack.attack_id} · round {round}</p>
            <h4 className="font-semibold leading-snug">{human(attack.title)}</h4>
          </div>
          {status === "break" && <Badge tone="danger">{t("redteam.break")}</Badge>}
          {status === "holds" && <Badge tone="egress">{t("redteam.holds")}</Badge>}
          {status === "running" && <Badge tone="signal"><Spinner className="size-3" />Simulating</Badge>}
        </div>
        <ul className="flex flex-wrap gap-1.5">
          {attack.events.map((e, i) => <li key={i}><Badge tone="outline">{describeEvent(e as Record<string, unknown>, label)}</Badge></li>)}
        </ul>
        <a href={src.source_url} target="_blank" rel="noreferrer"
           className="group flex items-start gap-2 rounded-[var(--radius-control)] bg-surface-2 p-2 text-xs hover:bg-surface-3">
          <ExternalLink className="mt-0.5 size-3.5 shrink-0 text-signal" />
          <span className="min-w-0">
            <span className="font-medium text-ink group-hover:text-signal">{t("redteam.inspired_by")}: {src.incident}{src.year ? ` (${src.year})` : ""}</span>
            {src.evidence && <span className="mt-0.5 line-clamp-2 block text-muted">{src.evidence}</span>}
          </span>
        </a>
        {attack.rationale && <p className="text-sm text-muted">{attack.rationale}</p>}
        <ScriptCode attack={attack} />
        {run && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs tabular">
            <span>Peak <b>{fmtNum(run.metrics.peak_density_ppm2 ?? null, 1)}</b> per m²</span>
            <span>Danger <b>{fmtDuration(run.metrics.time_above_danger_s ?? 0)}</b></span>
            <span>95% out <b>{fmtDuration(run.metrics.evac_time_p95_s ?? run.metrics.evac_time_estimate_s ?? null)}</b></span>
            <Button size="sm" variant="ghost" className="ml-auto h-7" onClick={() => onShow(run.run_id)}><Eye />{t("redteam.view_run")}</Button>
          </div>
        )}
        {run?.is_break && run.break_reasons.length > 0 && (
          <ul className="space-y-0.5 text-xs text-danger">{run.break_reasons.map((r) => <li key={r}>· {r}</li>)}</ul>
        )}
        {fixes.length > 0 && (
          <div className="space-y-2 border-t border-border pt-2">
            <p className="flex items-center gap-1.5 text-xs font-semibold text-muted"><Wrench className="size-3.5" />Blue team fixes</p>
            {fixes.map(({ fix }) => {
              const fn = view.nodes[`fix:${fix.fix_id}`];
              const fr = fn ? view.runs[fn.run_id] : undefined;
              const kept = fn?.accepted;
              const items = [...(fix.patch?.ops ?? []).map((o) => describeOp(o as Record<string, unknown>, label)),
                             ...(fix.operational ?? []).map((e) => describeEvent(e as Record<string, unknown>, label))];
              return (
                <div key={fix.fix_id} className={cn("rounded-[var(--radius-control)] border p-2.5", kept ? "border-egress/40 bg-egress-soft/50" : "border-border")}>
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium leading-snug">{human(fix.title)}</p>
                    {kept === true && <Badge tone="egress"><Check />{t("redteam.accepted")}</Badge>}
                    {kept === false && <Badge tone="neutral"><X />{t("redteam.rejected")}</Badge>}
                    {fn?.status === "running" && <Spinner className="size-3.5" />}
                  </div>
                  <p className="mt-1 text-xs text-muted">{items.join(" · ")}</p>
                  <p className="mt-1 text-2xs text-muted">{(fix.extensions as Record<string, unknown> | undefined)?.generated_by === "rules" ? "Standard engineering response" : "Proposed by the blue team (AI)"} · cost {fix.cost_label}</p>
                  {fr && run && (
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-3 text-xs tabular">
                      <span>Peak {fmtNum(run.metrics.peak_density_ppm2 ?? null, 1)} → <b>{fmtNum(fr.metrics.peak_density_ppm2 ?? null, 1)}</b></span>
                      <span>Danger {fmtDuration(run.metrics.time_above_danger_s ?? 0)} → <b>{fmtDuration(fr.metrics.time_above_danger_s ?? 0)}</b></span>
                      <span className="ml-auto flex">
                        {run && <TimeTravel projectId={projectId} attack={attack} fix={fix} attackRunId={run.run_id} active={active} />}
                        <Button size="sm" variant="ghost" className="h-7" onClick={() => onShow(fr.run_id)}><Eye />Show</Button>
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </article>
  );
}

function FinalCard({ view, summary, onApply, applying, onShow, human }: {
  view: SessionView; summary: Record<string, unknown>; onApply: () => void; applying: boolean; onShow: (id: string) => void;
  human: (text: string) => string;
}) {
  const before = summary.before as Record<string, number | null> | null;
  const after = summary.after as Record<string, number | null> | null;
  const kept = (summary.accepted_fixes as string[] | undefined)?.length ?? 0;
  const recs = (summary.recommendations as string[] | undefined) ?? [];
  const row = (k: string, l: string, f: (v: number | null | undefined, m: Record<string, number | null>) => string) => (
    <tr className="border-t border-border">
      <td className="py-1.5 text-muted">{l}</td>
      <td className="py-1.5 text-right tabular">{before ? f(before[k], before) : "–"}</td>
      <td className="py-1.5 text-right font-semibold tabular">{after ? f(after[k], after) : "–"}</td>
    </tr>
  );
  // evacuation time (95%) is undefined when 95% never got out: say how many were left instead
  const evac = (v: number | null | undefined, m: Record<string, number | null>) =>
    v == null && (m.agents_not_evacuated ?? 0) > 0 ? `${fmtInt(m.agents_not_evacuated)} still inside` : fmtDuration(v ?? null);
  const final = after ?? before;
  const stillAtRisk = !!final && ((final.agents_not_evacuated ?? 0) > 0 || (final.time_above_danger_s ?? 0) >= 5);
  return (
    <section className={`rounded-[var(--radius-panel)] border p-4 ${stillAtRisk ? "border-caution/40 bg-caution-soft/40" : "border-egress/35 bg-egress-soft/40"}`}>
      <p className="flex items-center gap-2 font-semibold">
        {stillAtRisk ? <ShieldAlert className="size-5 text-caution" /> : <ShieldCheck className="size-5 text-egress" />}
        {stillAtRisk ? t("redteam.finished_at_risk") : t("redteam.finished")}
      </p>
      {typeof summary.judge_text === "string" && <p className="mt-2 text-sm leading-relaxed">{human(summary.judge_text)}</p>}
      {!summary.numbers_checked && <p className="mt-1 text-2xs text-muted">Summary generated from computed results.</p>}
      {before && (
        <table className="mt-3 w-full text-sm">
          <thead><tr className="text-xs text-muted"><th className="text-left font-normal">Worst attack</th><th className="text-right font-normal">Before</th><th className="text-right font-normal">After fixes</th></tr></thead>
          <tbody>
            {row("evac_time_p95_s", "Evacuation time (95%)", evac)}
            {row("peak_density_ppm2", "Peak density (per m²)", (v) => fmtNum(v ?? null, 1))}
            {row("time_above_danger_s", "Time above danger", (v) => fmtDuration(v ?? 0))}
          </tbody>
        </table>
      )}
      {recs.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">{recs.map((r) => <li key={r}>{human(r)}</li>)}</ul>}
      <div className="mt-3 flex flex-wrap gap-2">
        {kept > 0 && <Button variant="primary" onClick={onApply} disabled={applying}><Check />{t("redteam.apply_plan")} ({kept})</Button>}
        {typeof summary.final_run_id === "string" && <Button onClick={() => onShow(summary.final_run_id as string)}><Eye />Show fixed plan</Button>}
        {typeof summary.final_run_id === "string" && (
          <CompareButton finalRunId={summary.final_run_id as string} view={view} />
        )}
      </div>
      <p className="mt-2 text-2xs text-muted">Stopped because: {String(summary.stopped_reason ?? "")} · {view.fixesAccepted} fixes kept</p>
    </section>
  );
}

function CompareButton({ finalRunId, view }: { finalRunId: string; view: SessionView }) {
  const before = view.nodes["final:before"]?.run_id;
  const setActive = useUi((s) => s.setActiveRun);
  const setCompare = useUi((s) => s.setCompareRun);
  if (!before) return null;
  return (
    <Button onClick={() => { setActive(finalRunId); setCompare(before); }}><Columns2 />Compare before and after</Button>
  );
}

function ActivityFeed({ view }: { view: SessionView }) {
  if (!view.feed.length) return <p className="text-sm text-muted">Agent calls, tool calls and decisions appear here.</p>;
  return (
    <ol className="max-h-[420px] space-y-1.5 overflow-y-auto pr-1 scrollbar-thin">
      {[...view.feed].reverse().map((l) => (
        <li key={l.seq} className="flex gap-2 rounded-[var(--radius-control)] border border-border bg-surface px-2.5 py-1.5 text-xs">
          {l.type === "agent_call" ? <Bot className="mt-0.5 size-3.5 shrink-0 text-signal" /> : l.type === "tool_call" ? <Wrench className="mt-0.5 size-3.5 shrink-0 text-muted" /> : <Activity className={cn("mt-0.5 size-3.5 shrink-0", l.level === "warning" || l.level === "error" ? "text-caution" : "text-muted")} />}
          <div className="min-w-0 flex-1">
            <p className="font-medium">
              {l.type === "agent_call" ? `${l.agent} agent` : l.type === "tool_call" ? l.agent : "Note"}
              {l.type === "agent_call" && <span className="ml-1.5 font-normal text-muted tabular">{fmtTokens(l.tokens)} tokens · {((l.ms ?? 0) / 1000).toFixed(1)} s{l.ok === false ? " · repaired/partial" : ""}</span>}
            </p>
            <p className="text-muted">{l.summary}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}
