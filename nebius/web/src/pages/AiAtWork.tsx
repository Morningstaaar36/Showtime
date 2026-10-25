/** Step 2 of the guided journey (route `/p/:projectId/work`): honest progress of the AI test,
 * the latest finished simulation in 3D, and the attacks and fixes as they arrive. */
import { useQueryClient } from "@tanstack/react-query";
import { Check, CircleAlert, Code2, Coins, Cpu, DoorClosed, Filter, Hourglass, Loader2, Repeat2, Scale, ShieldAlert, ShieldCheck, Snail, Sparkles, Square, Swords, TriangleAlert, UsersRound, WifiOff, Wrench, X } from "lucide-react";
import type * as React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { qk, useProject, useRun, useRunVenue, useSession, useSessions, useStopSession } from "@/api/queries";
import { useSessionStream } from "@/api/useSessionStream";
import { SandboxFeed } from "@/journey/SandboxFeed";
import { ToolCalls } from "@/journey/ToolCalls";
import { Confirm } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";
import { ScriptCode } from "@/journey/ScriptCode";
import { runOutcome } from "@/lib/evidence";
import { JourneyShell } from "@/journey/JourneyShell";
import { type ScenarioKind, scenarioKind } from "@/journey/plan/gallery";
import { type NodeKey, pipelineNodes, workSteps } from "@/journey/workSteps";
import { fmtDuration, fmtInt, fmtMoney, fmtTokens } from "@/lib/format";
import { cn } from "@/lib/utils";
import { textHumanizer } from "@/lib/venueText";
import { useReplay } from "@/replay/useReplay";
import { SceneRoot } from "@/scene/SceneRoot";
import { usePlayback } from "@/state/playback";
import { useUi } from "@/state/ui";
import { PeopleLegend } from "@/panels/Overlays";
import { FloorSwitch } from "@/panels/FloorSwitch";
import { SourceLink } from "@/journey/SourceLink";

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function AiAtWorkPage() {
  const { projectId = "" } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const project = useProject(projectId);
  const sessions = useSessions(projectId);
  const sessionId = params.get("session") ?? sessions.data?.[0]?.id ?? null;
  const session = useSession(sessionId);
  const view = useSessionStream(sessionId);
  const stop = useStopSession();
  const [confirmStop, setConfirmStop] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const status = session.data?.status;
  const failed = status === "failed";
  const ended = view.ended || status === "finished" || status === "stopped" || failed;
  // move on automatically only for a test the organizer just started (not one reopened later)
  const sawLive = useRef(params.get("live") === "1");
  if (!ended && (status === "running" || status === "queued")) sawLive.current = true;

  useEffect(() => { useUi.getState().resetForProject(); usePlayback.getState().reset(); }, [projectId]);
  useEffect(() => {
    if (ended) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [ended]);
  // refresh what the plan screen reads, then move on when a session we watched finishes
  useEffect(() => {
    if (!ended || !sessionId) return;
    void qc.invalidateQueries({ queryKey: qk.session(sessionId) });
    void qc.invalidateQueries({ queryKey: qk.sessions(projectId) });
    void qc.invalidateQueries({ queryKey: qk.runs(projectId) });
    if (!sawLive.current || failed || reducedMotion()) return;
    const id = window.setTimeout(() => navigate(`/p/${projectId}?session=${sessionId}`), 2000);
    return () => window.clearTimeout(id);
  }, [ended, failed, sessionId, projectId, navigate, qc]);

  const steps = workSteps(view.phases, { ended, failed, now });
  const current = steps.find((s) => s.status === "running");
  const finishedSteps = steps.filter((s) => s.status === "done" || s.status === "skipped").length;
  const percent = ended ? 100 : Math.round(((finishedSteps + (current ? 0.5 : 0)) / Math.max(steps.length, 1)) * 100);
  const doneNodes = Object.values(view.nodes).filter((n) => n.status !== "running" && n.status !== "pending");
  const runId = doneNodes[doneNodes.length - 1]?.run_id ?? null;
  const run = useRun(runId);
  const finishedRun = run.data && (run.data.status === "ok" || run.data.status === "partial") ? runId : null;
  const replay = useReplay(finishedRun, true);
  const runVenue = useRunVenue(finishedRun);
  useEffect(() => {
    if (!replay.data) return;
    usePlayback.getState().setDuration(replay.data.traj.duration);
    usePlayback.getState().setT(0);
    usePlayback.getState().play();
  }, [replay.data]);

  const venue = project.data?.version.venue;
  const human = useMemo(() => (venue ? textHumanizer(venue) : (s: string) => s), [venue]);
  const okRuns = Object.values(view.runs).length;

  if (!sessionId && !sessions.isLoading) {
    return (
      <JourneyShell step="work" projectId={projectId} title={project.data?.name}>
        <main id="main" className="mx-auto w-full max-w-2xl p-6">
          <EmptyState title={t("work.none")} body={t("work.none_body")}>
            <Button asChild variant="primary" size="lg"><Link to={`/p/${projectId}/describe`}>{t("work.go_check")}</Link></Button>
          </EmptyState>
        </main>
      </JourneyShell>
    );
  }

  const cards = [
    ...view.attacks.map(({ attack }) => {
      const node = view.nodes[`atk:${attack.attack_id}`];
      const r = node ? view.runs[node.run_id] : undefined;
      return { id: attack.attack_id, kind: "attack" as const, title: human(attack.title), status: r ? runOutcome(r) : node?.status === "running" ? "running" : "waiting", source: attack.inspired_by, attack };
    }),
    ...view.fixes.map(({ fix }) => {
      const node = view.nodes[`fix:${fix.fix_id}`];
      return { id: fix.fix_id, kind: "fix" as const, title: human(fix.title), status: node?.accepted === true ? "kept" : node?.accepted === false ? "not_kept" : "testing", source: null, attack: null };
    }),
  ];
  const visible = showAll ? cards : cards.slice(-8);
  const nodes = pipelineNodes(view.phases, { ended, failed, now });
  const breaks = view.scoreboard.reduce((n, r) => n + r.breaks, 0);
  const attacksTried = view.scoreboard.reduce((n, r) => n + r.attacks, 0) || view.attacks.length;
  const nodeCount: Record<NodeKey, number | null> = {
    red_team: view.attacks.length || null,
    screen: view.attacks.filter(({ attack }) => !!view.nodes[`atk:${attack.attack_id}`]).length || null,
    simulate: okRuns || null,
    fix: view.fixes.length || null,
    judge: null,
  };
  const budget = view.cost?.budget_tokens ?? 0;
  const used = view.cost?.tokens_total ?? 0;
  const startedAt = view.phases[0] ? Date.parse(view.phases[0].ts) : null;
  const lastAt = view.phases[view.phases.length - 1] ? Date.parse(view.phases[view.phases.length - 1].ts) : null;
  const elapsed = startedAt != null ? Math.max(0, ((ended ? lastAt ?? now : now) - startedAt) / 1000) : null;

  return (
    <JourneyShell step="work" projectId={projectId} title={project.data?.name} back={{ to: `/p/${projectId}`, label: t("journey.your_plan") }} wide>
      <Confirm open={confirmStop} onOpenChange={setConfirmStop} title={t("work.stop_title")} body={t("work.stop_body")}
               confirmLabel={t("work.stop")} onConfirm={() => sessionId && stop.mutate(sessionId)} />
      <main id="main" className="mx-auto flex w-full min-w-0 max-w-[1500px] flex-1 flex-col gap-4 p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="min-w-0 flex-1">
            <h1 className="text-2xl font-bold tracking-tight">{ended ? (failed ? t("work.failed_title") : t("work.done_title")) : t("work.title")}</h1>
            <p className="text-sm text-muted tabular">
              {ended ? t("work.all_done") : t("work.step_of", { n: Math.min(finishedSteps + 1, steps.length), total: steps.length })}
              {elapsed != null && ` · ${fmtDuration(elapsed)}`}{!ended && ` · ${t("work.leave_short")}`}
            </p>
          </div>
          {!ended && <Button className="h-11" disabled={stop.isPending} onClick={() => setConfirmStop(true)}><Square className="size-3.5" />{t("work.stop")}</Button>}
          {ended && !failed && (
            <Button asChild variant="primary" size="lg"><Link to={`/p/${projectId}?session=${sessionId}`} autoFocus><Sparkles />{t("work.open_plan")}</Link></Button>
          )}
        </div>
        {failed && <ErrorState message={session.data?.error || t("work.failed_body")} />}

        {/* the pipeline: each agent lights up as its events arrive */}
        <section aria-label={t("work.progress")} className="rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
          <div className="h-2 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label={t("work.progress")}>
            <div className={cn("h-full rounded-full transition-all duration-700", failed ? "bg-danger" : "bg-[linear-gradient(90deg,var(--sky),var(--signal),var(--pink))]")} style={{ width: `${percent}%` }} />
          </div>
          <ol className="mt-4 grid grid-cols-5 items-start">
            {nodes.map((n, i) => {
              const on = n.status === "running";
              const done = n.status === "done";
              const next = nodes[i + 1];
              return (
                <li key={n.key} className="relative flex flex-col items-center gap-1.5 text-center">
                  {next && (
                    <span aria-hidden className={cn("absolute left-[calc(50%+1.9rem)] right-[calc(-50%+1.9rem)] top-7 h-1 rounded-full max-sm:left-[calc(50%+1.4rem)] max-sm:right-[calc(-50%+1.4rem)] max-sm:top-5",
                      next.status === "running" && done ? "animate-flow" : done && next.status !== "pending" ? "bg-signal" : "bg-surface-3")} />
                  )}
                  <span className={cn("relative grid size-14 place-items-center rounded-full border-2 transition-all duration-500 [&_svg]:size-6 max-sm:size-10 max-sm:[&_svg]:size-5",
                    on ? "animate-halo scale-110 border-signal bg-signal text-signal-ink" : done ? "border-signal bg-signal-soft text-signal"
                      : n.status === "failed" ? "border-danger bg-danger-soft text-danger" : "border-border bg-surface-2 text-line")}>
                    {NODE_ICON[n.key]}
                    {nodeCount[n.key] != null && (
                      <span className="absolute -right-1 -top-1 grid min-w-6 place-items-center rounded-full bg-ink px-1.5 text-2xs font-bold text-plan tabular">{nodeCount[n.key]}</span>
                    )}
                  </span>
                  <span className={cn("text-sm font-semibold max-sm:text-2xs", n.status === "pending" || n.status === "skipped" ? "text-muted" : "text-ink")}>{t(`work.node_${n.key}`)}</span>
                  <span className="text-2xs text-muted tabular max-sm:hidden">{n.elapsedS != null ? fmtDuration(n.elapsedS) : n.status === "skipped" ? t("work.skipped_short") : " "}</span>
                </li>
              );
            })}
          </ol>
          <p className="sr-only" aria-live="polite">{current ? t(`work.step_${current.key}`) : ended ? t("work.done_title") : ""}</p>
          <div className="mt-3 flex min-h-11 items-center gap-3 rounded-[10px] bg-surface-2 px-3 py-2">
            {ended ? (failed ? <CircleAlert className="size-5 shrink-0 text-danger" /> : <Check className="size-5 shrink-0 text-egress" />) : <Loader2 className="size-5 shrink-0 animate-spin text-signal" />}
            <span className="min-w-0">
              <span className="block font-semibold">{current ? t(`work.step_${current.key}`) : ended ? (status === "stopped" ? t("work.stopped_ready") : t("work.ready")) : t("work.starting")}</span>
              {!ended && view.message && <span className="block truncate text-sm text-muted">{human(view.message)}</span>}
            </span>
            {!view.connected && !ended && view.lastSeq > 0 && <span className="ml-auto flex items-center gap-1.5 text-sm text-muted"><WifiOff className="size-4" />{t("work.reconnecting")}</span>}
          </div>
        </section>

        <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="relative h-[45vh] min-h-72 overflow-hidden rounded-[var(--radius-panel)] border border-border lg:h-auto lg:min-h-[380px]">
            {venue && <FloorSwitch venue={venue} className="absolute right-3 top-3 z-50" />}
            {venue ? (
              <SceneRoot venue={runVenue.data ?? venue} replay={replay.data ?? null} hotspots={[]} marshals={[]} editable={false}
                         resetNonce={0} quality="low" onExitClick={() => {}} onObjectClick={() => {}} onFloorClick={() => {}}
                         onFloorDoubleClick={() => {}} onMove={() => {}} onHotspot={() => {}} />
            ) : <Skeleton className="m-4 h-[calc(100%-2rem)]" />}
            <PeopleLegend replay={replay.data} className="absolute bottom-3 left-3 z-40 w-52" />
            <span className="pointer-events-none absolute left-3 top-3 z-40 inline-flex items-center gap-1.5 rounded-full bg-surface/95 px-3 py-1 text-sm shadow-sm">
              <span className={cn("size-2 rounded-full", replay.data ? "bg-egress" : "animate-pulse bg-line")} />
              {replay.data ? t("work.showing_latest") : t("work.waiting_sim")}
            </span>
          </div>

          <aside aria-label={t("work.scoreboard")} className="space-y-3">
            <dl className="grid grid-cols-2 gap-2">
              {([["attacks", attacksTried, "text-ink", <Swords key="a" />], ["breaks", breaks, breaks ? "text-danger" : "text-ink", <ShieldAlert key="b" />],
                ["fixes", view.fixesAccepted, "text-signal", <Wrench key="c" />], ["sims", okRuns, "text-ink", <Cpu key="d" />]] as const).map(([k, v, c, icon]) => (
                <div key={k} className="rounded-[var(--radius-panel)] border border-border bg-surface p-3 shadow-sm">
                  <dt className="flex items-center gap-1.5 text-xs text-muted [&_svg]:size-3.5">{icon}{t(`work.sb_${k}`)}</dt>
                  <dd className={cn("mt-1 text-3xl font-bold leading-none tabular transition-all", c)}>{fmtInt(v)}</dd>
                </div>
              ))}
            </dl>
            <div className="rounded-[var(--radius-panel)] border border-border bg-surface p-3 shadow-sm">
              <p className="flex items-center justify-between gap-2 text-xs text-muted"><span className="flex items-center gap-1.5"><Coins className="size-3.5" />{t("work.ai_meter")}</span>
                <span className="font-semibold text-ink tabular">{fmtMoney(view.cost?.cost_usd ?? session.data?.cost_usd ?? 0)}</span></p>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-surface-3"><div className="h-full rounded-full bg-signal transition-all duration-700" style={{ width: `${budget ? Math.min(100, (used / budget) * 100) : 0}%` }} /></div>
              <p className="mt-1 text-2xs text-muted tabular">{budget ? t("work.tokens_of", { n: fmtTokens(used), max: fmtTokens(budget) }) : t("work.tokens", { n: fmtTokens(used || (session.data?.tokens ?? 0)) })}</p>
            </div>
            <ToolCalls feed={view.feed} />
            <SandboxFeed runs={view.sandboxes} />
          </aside>
        </div>

        <section aria-label={t("work.trying")} className="space-y-2">
          <div className="flex items-baseline justify-between">
            <h2 className="font-semibold">{t("work.trying")}</h2>
            {cards.length > 8 && <Button variant="link" onClick={() => setShowAll((v) => !v)}>{showAll ? t("work.show_less") : t("work.show_all", { n: cards.length })}</Button>}
          </div>
          {cards.length === 0 ? <p className="text-sm text-muted">{ended ? t("work.no_cards") : t("work.cards_soon")}</p> : (
            <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-4">
              {visible.map((c) => (
                <li key={`${c.kind}:${c.id}`} className={cn("animate-deal-in flex min-w-0 gap-3 rounded-[var(--radius-panel)] border-2 bg-surface p-3 text-sm shadow-sm",
                                                             c.status === "break" ? "border-danger/35" : c.status === "holds" || c.status === "kept" ? "border-egress/30" : "border-border")}>
                  <span className={cn("grid size-10 shrink-0 place-items-center rounded-[10px] [&_svg]:size-5",
                                      c.kind === "attack" ? "bg-danger-soft text-danger-strong" : "bg-signal-soft text-signal")} aria-hidden>
                    {c.kind === "attack" ? KIND_ICON[scenarioKind(c.attack)] : <Wrench />}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <p className="line-clamp-2 font-semibold leading-snug">{c.title}</p>
                      {c.status === "break" && <Badge tone="danger"><X />{t("work.breaks")}</Badge>}
                      {c.status === "holds" && <Badge tone="egress"><Check />{t("work.holds")}</Badge>}
                      {c.status === "preview" && <Badge tone="neutral">{t("work.preview")}</Badge>}
                      {c.status === "unknown" && <Badge tone="neutral">{t("work.unknown")}</Badge>}
                      {c.status === "kept" && <Badge tone="egress"><Check />{t("work.kept")}</Badge>}
                      {c.status === "not_kept" && <Badge tone="neutral">{t("work.not_kept")}</Badge>}
                      {(c.status === "running" || c.status === "testing") && <Badge tone="signal"><Loader2 className="animate-spin" />{t("work.testing")}</Badge>}
                    </div>
                    <p className="text-xs text-muted">{c.kind === "attack" ? t("work.risk") : t("work.fix")}</p>
                    <SourceLink source={c.source} />
                    <ScriptCode attack={c.attack} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </main>
    </JourneyShell>
  );
}

const NODE_ICON: Record<NodeKey, React.ReactNode> = {
  red_team: <Swords />, screen: <Filter />, simulate: <Cpu />, fix: <Wrench />, judge: <Scale />,
};

const KIND_ICON: Record<ScenarioKind, React.ReactNode> = {
  block: <DoorClosed />, surge: <UsersRound />, slow: <Snail />, counter: <Repeat2 />, hold: <Hourglass />,
  script: <Code2 />, normal: <ShieldCheck />, other: <TriangleAlert />,
};
