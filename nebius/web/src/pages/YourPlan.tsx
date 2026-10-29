/** Step 3 of the guided journey (route `/p/:projectId`): the tested plan as three tabs.
 * Overview (one verdict about the plan as it stands, the key numbers, the replay before / after /
 * side by side on one clock, before vs after), Fixes (the AI's tested fixes to accept) and Hand
 * over (report, map, checklist, data). Scenarios, sandboxes, floors and the deeper checks are in
 * Expert view › Analysis. Every number comes from a run of a known venue version and says what it
 * is based on. */
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { Check, Download, LayoutDashboard, MessageCircleQuestion, RotateCcw, Send, ShieldQuestion, Waves, Wrench } from "lucide-react";
import type * as React from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useApplyFixes, usePlan, useProject, useRun, useRunVenue, useSession, useSessions, useSettings, useStartSession, useStartTogether, useTestModes, useTogether, useUndo, useVersions } from "@/api/queries";
import type { Fix, RunOut } from "@/api/types";
import { useSessionStream } from "@/api/useSessionStream";
import { Button } from "@/components/ui/button";
import { Skeleton, Spinner } from "@/components/ui/misc";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { TabsContent } from "@/components/ui/tabs";
import { t } from "@/i18n";
import { AskAnything } from "@/journey/AskAnything";
import type { ProposalPreview } from "@/journey/AskChange";
import { JourneyShell } from "@/journey/JourneyShell";
import { CostCard } from "@/journey/plan/CostCard";
import { FixChooser } from "@/journey/plan/FixChooser";
import { acceptBody, fixDependencies, toggleFix } from "@/journey/plan/fixes";
import { HandOver } from "@/journey/plan/HandOver";
import { ANALYSIS_TABS } from "@/journey/plan/MoreAnalysis";
import { Overview, type SessionMetrics } from "@/journey/plan/Overview";
import { FOCUS_FROM } from "@/scene/geom";
import { usePressure } from "@/journey/plan/pressure";
import { sandboxRows, scriptOutcomes } from "@/journey/plan/sandboxes";
import { ReplayStage } from "@/journey/plan/ReplayStage";
import { SavedActions } from "@/journey/plan/SavedActions";
import { ScenarioList } from "@/journey/plan/ScenarioViewer";
import { type ScenarioRow, scenarioMarkers, scenarioRows } from "@/journey/plan/scenarios";
import { planState } from "@/journey/plan/state";
import { RealCaseCard } from "@/journey/RealCases";
import { realCaseOf, simulatedPeak } from "@/journey/realCases";
import { runBasisLabel } from "@/lib/evidence";
import { fmtNum, fmtClock, withoutRunIds } from "@/lib/format";
import { cn, UNDO_TOAST_ID } from "@/lib/utils";
import { displayNames, textHumanizer } from "@/lib/venueText";
import { FloorSwitch } from "@/panels/FloorSwitch";
import { Timeline } from "@/panels/Timeline";
import { type Thresholds, thresholdsOf, verdictOf } from "@/panels/verdict";
import type { Replay } from "@/replay/useReplay";
import { useReplay } from "@/replay/useReplay";
import { SceneRoot } from "@/scene/SceneRoot";
import { usePlayback } from "@/state/playback";
import { useUi } from "@/state/ui";
import { savedTestMode, testModesOf } from "@/journey/testModes";

const PLAN_TABS = ["overview", "fixes", "handover"] as const;
type PlanTab = (typeof PLAN_TABS)[number];

const TabsPrimitiveList = TabsPrimitive.List;
const TabsPrimitiveTrigger = TabsPrimitive.Trigger;
const Tabs = TabsPrimitive.Root;

const usable = (r: RunOut | undefined) => !!r && (r.status === "ok" || r.status === "partial");
const noop = () => {};

/** A run's numbers in the shape of the session's before/after summary (for a version that
 * holds only some of the kept fixes, whose own run is the "after"). */
function metricsOf(run: { result?: { metrics?: Record<string, unknown> | null } | null } | undefined): SessionMetrics | undefined {
  const m = run?.result?.metrics as (Record<string, unknown> & { extra?: Record<string, unknown> }) | undefined;
  if (!m) return undefined;
  return {
    evac_time_p95_s: m.evac_time_p95_s ?? null,
    evac_time_estimate_s: m.evac_time_p95_s == null ? m.extra?.rset_extrapolated_s ?? null : null,
    peak_density_ppm2: m.peak_density_ppm2 ?? null,
    time_above_danger_s: m.time_above_danger_s ?? null,
    agents_not_evacuated: m.agents_not_evacuated ?? null,
  } as SessionMetrics;
}

export function YourPlanPage() {
  const { projectId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const project = useProject(projectId);
  const selectedPlan = usePlan(projectId);
  const versions = useVersions(projectId);
  const settings = useSettings();
  const testModes = testModesOf(useTestModes().data);
  const sessions = useSessions(projectId);
  const sessionId = params.get("session") ?? sessions.data?.[0]?.id ?? null;
  const session = useSession(sessionId);
  const summary = session.data?.summary ?? null;
  const ended = session.data?.status === "finished" || session.data?.status === "stopped";
  const view = useSessionStream(ended ? sessionId : null);
  const apply = useApplyFixes(projectId);
  const undo = useUndo(projectId);
  const start = useStartSession();
  // the tab lives in the URL (?tab=fixes), so a link or a reload opens the same view; an unknown
  // tab is the Overview, for every hook below too. Older links keep working: the replay is on
  // the Overview, and scenarios, sandboxes and floors open Expert view's analysis
  const wanted = params.get("tab") ?? "overview";
  const tab: PlanTab = (PLAN_TABS as readonly string[]).includes(wanted) ? (wanted as PlanTab) : "overview";
  const expertTab = (ANALYSIS_TABS as readonly string[]).includes(wanted) ? wanted : null;
  const go = (next: PlanTab) => setParams((prev) => {
    const q = new URLSearchParams(prev);
    if (next === "overview") q.delete("tab"); else q.set("tab", next);
    return q;
  }, { replace: true });
  // the replay: before, after, or both side by side on one clock (null: the plan as it stands)
  const [mode, setMode] = useState<"before" | "after" | "split" | null>(null);
  const [turbulence, setTurbulence] = useState(false);
  const [proposal, setProposal] = useState<ProposalPreview | null>(null);
  // the organizer's choice of kept fixes, per session (default: all of them)
  const [choice, setChoice] = useState<{ sid: string | null; ids: Set<string> } | null>(null);
  // a scenario picked from the list replays instead of the before/after pair
  const [picked, setPicked] = useState<{ sid: string | null; row: ScenarioRow } | null>(null);

  useEffect(() => { useUi.getState().resetForProject(); usePlayback.getState().reset(); }, [projectId]);

  // a version holding only some kept fixes rests on its own run once they were simulated together
  const currentHash = project.data?.version.plan_hash;
  const subsetRecord = [...(summary?.applied ?? [])].reverse().find((r) => r.plan_hash === currentHash && r.together) ?? null;
  const subsetRun = subsetRecord?.together?.status === "done" ? subsetRecord.together.run_id : null;
  const togetherCheck = useTogether(sessionId, !!summary?.applied?.some((r) => !r.tested_together || r.together));
  const startTogether = useStartTogether(sessionId);
  const afterId = subsetRun ?? summary?.final_run_id ?? null;
  const worstNode = summary?.worst_attack_id ? view.nodes[`atk:${summary.worst_attack_id}`]?.run_id : undefined;
  const beforeId = view.nodes["final:before"]?.run_id ?? worstNode ?? summary?.baseline_run_id ?? null;
  const after = useRun(afterId);
  const before = useRun(beforeId);
  // a rebuilt real case: its "as it happened" run is the session's baseline
  const caseCard = realCaseOf(project.data?.version.venue);
  const caseRun = useRun(caseCard ? summary?.baseline_run_id ?? null : null);
  const hasAfter = usable(after.data);
  const beforeOk = usable(before.data) ? before.data!.id : null;
  const afterOk = hasAfter ? after.data!.id : null;
  const onOverview = tab === "overview";
  const beforeReplay = useReplay(beforeOk, onOverview);
  const afterReplay = useReplay(afterOk, true);
  const beforeVenue = useRunVenue(beforeOk);
  const kept = useMemo<Fix[]>(() => {
    const fixes = summary?.fixes ?? [];
    return (summary?.accepted_fixes ?? []).map((id) => fixes.find((f) => f.fix_id === id)).filter((f): f is Fix => !!f);
  }, [summary]);
  const testedHash = versions.data?.find((v) => v.version === session.data?.venue_version)?.plan_hash;
  const { state, record } = planState({ currentHash: project.data?.version.plan_hash, testedHash, kept: kept.length,
    applied: summary?.applied, fixedHash: after.data?.evidence?.plan_hash });
  // the plan as it stands today: without the fixes while they wait to be accepted, else with them
  const deciding = state === "pending" && kept.length > 0;
  const todayIsAfter = hasAfter && !deciding;
  const side = mode ?? (todayIsAfter ? "after" : "before");
  const shownSide: "before" | "after" = hasAfter && side !== "before" ? "after" : "before";
  const pickedRow = picked && picked.sid === sessionId ? picked.row : null;
  const pickedRun = useRun(pickedRow?.runId ?? null);
  const shown = pickedRow ? pickedRun.data : shownSide === "after" ? after.data : before.data;
  const shownId = usable(shown) ? shown!.id : null;
  const replay = useReplay(shownId, true);
  const shownVenue = useRunVenue(shownId);
  const split = side === "split" && !pickedRow && hasAfter && !!beforeOk;
  const pressure = usePressure(shownId, onOverview);
  const turb = turbulence && !split && pressure.data ? pressure.data : null;
  // one clock: the Overview's replay drives it; a plan's replay starts just before its worst moment
  const clockReplay = onOverview ? replay.data : null;
  // a tall building opens on one floor: the one where the crowd was densest, not always the ground
  const peakFloor = useMemo(() => {
    const idx = clockReplay?.density?.index;
    if (!idx?.peak_map?.length) return null;
    let best = -1, at: string | null = null;
    idx.peak_map.forEach((rows, f) => {
      const top = Math.max(0, ...rows.map((r) => Math.max(0, ...r)));
      if (top > best) { best = top; at = idx.floors[f] ?? null; }
    });
    return at;
  }, [clockReplay]);
  useEffect(() => {
    const storeys = project.data?.version.venue.floors.length ?? 0;
    // only where "auto" would focus one floor anyway (two floors are shown together)
    if (peakFloor && storeys >= FOCUS_FROM && useUi.getState().floorView === "auto") useUi.getState().setFloorView(peakFloor);
  }, [peakFloor, project.data]);
  const compareReplay = onOverview && split ? beforeReplay.data : null;
  const picking = !!pickedRow;
  useEffect(() => {
    if (!clockReplay) return;
    const pb = usePlayback.getState();
    pb.setDuration(Math.max(clockReplay.traj.duration, compareReplay?.traj.duration ?? 0));
    // a scenario picked from the list plays from its start, where its events begin
    const peak = picking ? null : peakMoment(clockReplay);
    pb.setT(peak != null ? Math.max(0, peak - 12) : 0);
    pb.play();
  }, [clockReplay, compareReplay, picking]);
  // an old ?tab=replay link lands on the Overview's replay
  const scrolled = useRef(false);
  const replayRef = (el: HTMLDivElement | null) => {
    if (el && wanted === "replay" && !scrolled.current) { scrolled.current = true; el.scrollIntoView({ block: "start" }); }
  };

  const p = project.data;
  const venue = p?.version.venue;
  const names = useMemo(() => new Map([
    ...(shownVenue.data ? displayNames(shownVenue.data) : []),
    ...(venue ? displayNames(venue) : []),
  ]), [venue, shownVenue.data]);
  const human = useMemo(() => {
    const current = venue ? textHumanizer(venue) : (s: string) => s;
    const tested = shownVenue.data ? textHumanizer(shownVenue.data) : (s: string) => s;
    return (s: string) => current(tested(s));
  }, [venue, shownVenue.data]);
  const deps = useMemo(() => fixDependencies(kept), [kept]);
  const rows = useMemo(() => scenarioRows(view.nodes, view.runs, summary?.attacks ?? [], summary?.fixes ?? [], human),
    [view.nodes, view.runs, summary, human]);

  if (expertTab) {
    const q = new URLSearchParams(params);
    q.set("tab", expertTab);
    return <Navigate to={`/p/${projectId}/expert/analysis?${q}`} replace />;
  }
  if (project.isError) {
    const missing = (project.error as { status?: number }).status === 404;
    return (
      <JourneyShell step="plan">
        <main id="main" className="mx-auto w-full max-w-2xl space-y-4 p-8">
          <ErrorState title={missing ? t("yourplan.missing") : undefined} message={missing ? t("yourplan.missing_body") : (project.error as Error).message}
                      onRetry={missing ? undefined : () => project.refetch()} />
          <Button variant="primary" onClick={() => navigate("/")}>{t("journey.home")}</Button>
        </main>
      </JourneyShell>
    );
  }
  if (!p || !venue || sessions.isLoading) {
    return (
      <JourneyShell step="plan" projectId={projectId}>
        <main className="mx-auto w-full max-w-6xl space-y-4 p-4"><Skeleton className="h-24" /><div className="grid grid-cols-1 gap-3 sm:grid-cols-3"><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /></div><Skeleton className="h-80" /></main>
      </JourneyShell>
    );
  }

  const label = (id: string) => names.get(id) ?? id;
  // the depth this browser chose last on "Test this plan"
  const testAgain = () => start.mutate({ project_id: p.id, config: savedTestMode(testModes).config }, {
    onSuccess: (s) => navigate(`/p/${p.id}/work?session=${s.id}&live=1`),
    onError: (e) => toast.error(e.message),
  });

  // --- untested, running or failed: one obvious next step each ------------------------------
  const status = session.data?.status;
  if (!sessionId || !status || status === "running" || status === "queued" || status === "failed") {
    return (
      <JourneyShell step="plan" projectId={p.id} title={p.name} back={{ to: "/", label: t("journey.home") }}>
        <main id="main" className="mx-auto w-full max-w-6xl space-y-4 p-4">
          <h1 className="text-2xl font-semibold tracking-tight">{p.name}</h1>
          {/* a real case shows what happened and its sources while its first test still runs */}
          {caseCard && <RealCaseCard card={caseCard} peak={null} />}
          {!sessionId && (
            <EmptyState icon={<ShieldQuestion />} title={t("yourplan.untested")} body={t("yourplan.untested_body")}>
              <Button asChild variant="primary" size="lg"><Link to={`/p/${p.id}/describe`}>{t("yourplan.check_and_test")}</Link></Button>
            </EmptyState>
          )}
          {(status === "running" || status === "queued") && (
            <EmptyState icon={<Spinner />} title={t("yourplan.running")} body={t("yourplan.running_body")}>
              <Button asChild variant="primary" size="lg"><Link to={`/p/${p.id}/work?session=${sessionId}`}>{t("yourplan.watch")}</Link></Button>
            </EmptyState>
          )}
          {status === "failed" && (
            <div className="space-y-3">
              <ErrorState title={t("yourplan.failed")} message={session.data?.error || t("work.failed_body")} />
              <Button variant="primary" size="lg" onClick={testAgain} disabled={start.isPending}><RotateCcw />{t("yourplan.test_again")}</Button>
            </div>
          )}
          <div className="relative isolate h-[50vh] overflow-hidden rounded-[10px] border border-border">
            <FloorSwitch venue={venue} className="absolute left-3 top-3 z-50" />
            <SceneRoot venue={venue} replay={null} hotspots={[]} marshals={[]} editable={false} resetNonce={0} quality="low"
                       onExitClick={noop} onObjectClick={noop} onFloorClick={noop} onFloorDoubleClick={noop} onMove={noop} onHotspot={noop} />
          </div>
        </main>
      </JourneyShell>
    );
  }

  // --- tested ------------------------------------------------------------------------------
  const eff = settings.data?.effective ?? {};
  const th: Thresholds = thresholdsOf(eff);
  const keptIds = kept.map((f) => f.fix_id);
  const selected = choice && choice.sid === sessionId ? choice.ids : new Set(keptIds);
  const toggle = (id: string) => setChoice({ sid: sessionId, ids: toggleFix(selected, id, deps) });
  const accept = () => sessionId && apply.mutate({ sessionId, ...acceptBody(selected, keptIds) }, {
    onSuccess: (r) => toast.success(t("yourplan.accepted", { n: r.version.version }), {
      id: UNDO_TOAST_ID,
      description: r.applied && !r.applied.tested_together ? t("yourplan.subset_note") : undefined,
      action: { label: t("common.undo"), onClick: () => undo.mutate() },
    }),
    onError: (e) => toast.error(e.message, { description: (e as { hint?: string | null }).hint ?? undefined }),
  });

  const todayOut = todayIsAfter ? after.data : usable(before.data) ? before.data : hasAfter ? after.data : undefined;
  const todayRun = todayOut?.result ?? null;
  const verdict = verdictOf(todayRun, th, label);
  const basis = runBasisLabel(todayRun);
  // while fixes wait: today's verdict, then what the tested fixes make of it, in one sentence
  const fixed = deciding && hasAfter ? verdictOf(after.data?.result ?? null, th, label).level : null;
  const headline = !todayRun ? t("yourplan.no_result")
    : fixed ? t("plan.hero_deciding", { today: t(`plan.hero_today_${verdict.level}`), fix: t(`plan.hero_fix_${fixed}${kept.length === 1 ? "" : "_n"}`, { n: kept.length }) })
    : verdict.headline;
  const cd = summary?.countdown;
  const cdBasis = [(cd?.status === "ok" || cd?.status === "too_late") ? cd.hazard_explanation : "",
    withoutRunIds(cd?.rset_source) ? t("yourplan.cd_from", { source: withoutRunIds(cd?.rset_source) }) : t("yourplan.cd_source")].filter(Boolean).join(" · ");
  const worst = summary?.attacks?.find((a) => a.attack_id === summary.worst_attack_id);
  // organizers read the AI's words without internal run ids
  const clean = (s: string) => withoutRunIds(human(s));
  const judge = summary?.judge_text ? `${clean(summary.judge_text)}${summary.numbers_checked ? ` ${t("yourplan.numbers_checked")}` : ""}` : null;
  const attackTitle = (id: string) => summary?.attacks?.find((a) => a.attack_id === id)?.title ?? id;
  const allFixes = summary?.fixes ?? [];
  const markersFor = (row: ScenarioRow | null, side: "before" | "after") => {
    if (row) {
      const atk = summary?.attacks?.find((a) => a.attack_id === row.attackId);
      const parent = row.kind === "fix" ? rows.find((r) => r.children.some((c) => c.key === row.key)) : undefined;
      const attackOf = atk ?? summary?.attacks?.find((a) => a.attack_id === parent?.attackId);
      const fixesOf = row.kind === "fix" ? allFixes.filter((f) => f.fix_id === row.fixId)
        : row.key === "final:after" || row.key.includes(":current:") ? kept : [];
      return scenarioMarkers(attackOf, fixesOf, label);
    }
    return scenarioMarkers(worst, side === "after" ? kept : [], label);
  };
  const pick = (row: ScenarioRow) => { setPicked({ sid: sessionId, row }); usePlayback.getState().setT(0); };
  const previewing = !!proposal;
  const pending = deciding ? selected.size : 0;
  const reportUrl = api.url(`/sessions/${sessionId}/report`);
  const retest = state === "stale" || state === "accepted_subset";
  const sbx = sandboxRows(view).rows.length;
  const expertHref = (sub: string) => `/p/${p.id}/expert/analysis?session=${sessionId}&tab=${sub}`;

  // the page's one primary action, in the verdict
  const action = deciding ? (
    selected.size > 0
      ? <Button variant="primary" size="lg" onClick={accept} disabled={apply.isPending}><Check />{t(selected.size === 1 ? "plan.accept_fix" : "plan.accept_fixes", { n: selected.size })}</Button>
      : <Button variant="primary" size="lg" onClick={() => go("fixes")}><Wrench />{t("plan.review_fixes")}</Button>
  ) : retest ? (
    <Button variant="primary" size="lg" onClick={testAgain} disabled={start.isPending}><RotateCcw />{t("yourplan.test_again")}</Button>
  ) : (
    <Button variant="primary" size="lg" onClick={() => go("handover")}><Send />{t("plan.tab_handover")}</Button>
  );

  const stageBasis = shown ? runBasisLabel(shown.result) : t("evidence.basis.unknown");
  const segmented = (opts: { id: string; label: string }[], value: string, set: (v: string) => void, aria: string) => (
    <div role="group" aria-label={aria} className="pointer-events-auto flex rounded-full bg-surface/95 p-1 shadow-[var(--shadow-float)] backdrop-blur">
      {opts.map((o) => (
        <button key={o.id} type="button" aria-pressed={value === o.id} onClick={() => set(o.id)}
                className={cn("min-h-9 rounded-full px-4 text-sm font-semibold transition", value === o.id ? "bg-signal text-signal-ink shadow-sm" : "text-muted hover:text-ink")}>
          {o.label}
        </button>
      ))}
    </div>
  );
  const bothSides = hasAfter && usable(before.data);
  const sides = [{ id: "before", label: t("yourplan.before") }, { id: "after", label: t("yourplan.after") }, { id: "split", label: t("plan.side_by_side") }];

  const replaySection = (
    <div ref={replayRef} id="replay" className="grid min-w-0 scroll-mt-20 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0 space-y-2">
        <ReplayStage label={t("yourplan.replay")} className="h-[58vh] min-h-[360px]"
                     main={previewing ? { venue: proposal.venue, replay: null }
                       : { venue: shownVenue.data ?? venue, replay: replay.data && turb ? { ...replay.data, density: turb.grid } : replay.data ?? null }}
                     compare={!previewing && split ? { venue: beforeVenue.data ?? venue, replay: beforeReplay.data ?? null } : null}
                     highlights={previewing ? proposal.changes : undefined}
                     markers={markersFor(pickedRow, shownSide)} basis={previewing ? undefined : stageBasis}
                     legend={previewing ? null : turb ? { warn: turb.warn, danger: turb.danger, max: turb.max, title: t("plan.turbulence_scale", { unit: turb.unit ?? "" }).trim() } : th}
                     chip={!previewing && pickedRow ? <span className="block truncate rounded-full bg-surface/95 px-3 py-1 text-sm font-medium shadow-sm">{pickedRow.title}</span> : undefined}
                     top={previewing ? undefined : pickedRow
                       ? <Button size="sm" className="pointer-events-auto shadow-sm" onClick={() => setPicked(null)}>{t("yourplan.sc_back")}</Button>
                       : bothSides ? segmented(sides, side, (v) => setMode(v as "before" | "after" | "split"), t("yourplan.before_after"))
                       : undefined}
                     corner={pressure.data ? (
                       <button type="button" aria-pressed={turbulence} onClick={() => setTurbulence((v) => !v)}
                               className={cn("min-h-9 rounded-full px-3 text-xs font-semibold shadow-sm", turbulence ? "bg-signal text-signal-ink" : "bg-surface/95 text-ink")}>
                         <Waves className="mr-1 inline size-3.5" aria-hidden />{t("plan.turbulence")}
                         {turbulence && pressure.data.peak != null && <span className="ml-1 tabular">· {t("plan.turbulence_peak", { v: fmtNum(pressure.data.peak, 1), at: fmtClock(pressure.data.peakAtS ?? 0) })}</span>}
                       </button>) : undefined} />
        {!previewing && replay.data && <Timeline markers={markersFor(pickedRow, shownSide)} />}
        <section aria-labelledby="ask-h" className="space-y-2 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
          <h2 id="ask-h" className="flex items-center gap-2 font-semibold"><MessageCircleQuestion className="size-4 text-signal" aria-hidden />{t("ask.label")}</h2>
          <AskAnything project={p} context="plan" sessionId={sessionId} onPreview={setProposal} className="max-w-none" />
        </section>
      </div>
      <div className="min-w-0 space-y-4">
        <ScenarioList rows={rows} pickedRun={pickedRow?.runId ?? null} onPick={pick} attacks={summary?.attacks ?? []} />
        {selectedPlan.data && <SavedActions actions={selectedPlan.data.plan.actions} version={selectedPlan.data.version} projectId={p.id} name={label} />}
      </div>
    </div>
  );

  const tabs: { id: PlanTab; icon: React.ReactNode; label: string; badge?: number }[] = [
    { id: "overview", icon: <LayoutDashboard />, label: t("plan.tab_overview") },
    { id: "fixes", icon: <Wrench />, label: t("plan.tab_fixes"), badge: pending || undefined },
    { id: "handover", icon: <Send />, label: t("plan.tab_handover") },
  ];

  return (
    <JourneyShell step="plan" projectId={p.id} title={p.name} back={{ to: "/", label: t("journey.home") }}>
      <main id="main" className="mx-auto w-full min-w-0 max-w-6xl space-y-4 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight">{p.name}</h1>
            <p className="text-sm text-muted tabular">{t("yourplan.version", { n: p.current_version })}</p>
          </div>
          {/* secondary: the verdict holds the page's one primary action */}
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="secondary">
              <a href={reportUrl} target="_blank" rel="noreferrer"><Download />{t("yourplan.report")}</a>
            </Button>
            {!retest && <Button variant="secondary" onClick={testAgain} disabled={start.isPending}><RotateCcw />{t("yourplan.test_again")}</Button>}
          </div>
        </div>

        {state === "stale" && (
          <div role="status" className="flex flex-wrap items-center gap-3 rounded-[10px] border border-caution/40 bg-caution-soft p-3 text-sm">
            <ShieldQuestion className="size-5 shrink-0 text-caution" />
            <span className="min-w-0 flex-1">{t("yourplan.stale")}</span>
          </div>
        )}
        {status === "stopped" && <p role="status" className="rounded-[10px] border border-caution/40 bg-caution-soft p-3 text-sm">{t("yourplan.partial", { reason: summary?.stopped_reason ?? "" })}</p>}

        <Tabs value={tab} onValueChange={(v) => go(v as PlanTab)} className="space-y-4">
          <TabsPrimitiveList aria-label={t("plan.tabs")}
                             className="scrollbar-thin -mx-4 flex max-w-[100vw] gap-1 overflow-x-auto px-4 pb-1 sm:mx-0 sm:max-w-full sm:px-0">
            {tabs.map((x) => (
              <TabsPrimitiveTrigger key={x.id} value={x.id}
                                    className="group flex min-h-11 shrink-0 items-center gap-2 rounded-full border border-border bg-surface px-4 text-sm font-semibold text-muted shadow-sm transition hover:text-ink data-[state=active]:border-signal data-[state=active]:bg-signal data-[state=active]:text-signal-ink [&_svg]:size-4">
                {x.icon}{x.label}
                {x.badge != null && <span className="grid min-w-5 place-items-center rounded-full bg-surface-3 px-1.5 text-2xs text-ink tabular group-data-[state=active]:bg-surface/25 group-data-[state=active]:text-signal-ink">{x.badge}</span>}
              </TabsPrimitiveTrigger>
            ))}
          </TabsPrimitiveList>

          <TabsContent value="overview" className="animate-tab-in">
            <Overview level={todayRun ? verdict.level : "unknown"} headline={headline}
                      evaluation={subsetRun ? subsetRecord?.together?.evaluation : summary?.evaluation}
                      worst={worst ? human(worst.title) : null}
                      fixes={todayIsAfter ? (state === "accepted_subset" ? record?.fix_ids.length ?? kept.length : kept.length) : 0}
                      compared={hasAfter ? (state === "accepted_subset" ? record?.fix_ids.length ?? kept.length : kept.length) : 0}
                      reasons={verdict.reasons} run={todayRun} stoodIn={summary?.stood_in}
                      more={{ href: expertHref("scenarios"), sandboxesHref: expertHref("sandboxes"), runs: sbx, scripts: scriptOutcomes(view, summary?.attacks ?? []).length }}
                      basis={basis} countdown={cd} countdownBasis={cdBasis} th={th}
                      targetS={venue.mode === "indoor" ? th.targetIndoorS : th.targetOutdoorS}
                      before={summary?.before as SessionMetrics | undefined}
                      after={subsetRun ? metricsOf(after.data) : summary?.after as SessionMetrics | undefined}
                      insideSeries={insideSeries((todayIsAfter ? afterReplay.data : beforeReplay.data) ?? null)}
                      action={action} replay={replaySection}
                      summary={{ judge, reasons: (summary?.evaluation?.reasons ?? []).map(clean), recommendations: (summary?.recommendations ?? []).map(clean) }}
                      realCase={caseCard ? <RealCaseCard card={caseCard} peak={simulatedPeak(caseRun.data?.result, venue, label)} /> : undefined} />
          </TabsContent>

          <TabsContent value="fixes" className="animate-tab-in">
            <FixChooser kept={kept} selected={selected} deps={deps} onToggle={toggle} nodes={view.nodes} loading={!view.ended}
                        venue={venue} state={state} record={record} attackTitle={attackTitle} name={label} human={human}
                        onAccept={accept} accepting={apply.isPending} onTestAgain={testAgain} testing={start.isPending}
                        together={togetherCheck.data?.record?.plan_hash === record?.plan_hash ? togetherCheck.data?.record?.together : record?.together}
                        onTogether={() => startTogether.mutate(undefined, { onError: (e) => toast.error(e.message) })} togetherBusy={startTogether.isPending} />
          </TabsContent>

          <TabsContent value="handover" className="animate-tab-in">
            <HandOver sessionId={sessionId} projectId={p.id} venue={venue} projectName={p.name} onTestAgain={testAgain} testing={start.isPending}>
              <CostCard cost={summary?.cost} tokens={session.data?.tokens ?? 0} costUsd={session.data?.cost_usd ?? 0} />
            </HandOver>
          </TabsContent>
        </Tabs>
      </main>
    </JourneyShell>
  );
}

/** Seconds into the replay where density peaks (from the density index), a few seconds early. */
/** When the crowd was densest. `peak_series` has one value per trajectory frame (4 per second),
 * thinned to at most about 600 values by keeping every `step`-th frame (sim/metrics.py), so its
 * index maps to the trajectory's frame times, not to the density grid's stored frames. */
function peakMoment(r: Replay | null | undefined): number | null {
  const idx = r?.density?.index;
  const times = r?.traj.index.times;
  if (!idx?.peak_series?.length || !times?.length) return null;
  let k = 0;
  idx.peak_series.forEach((v, i) => { if (v > idx.peak_series[k]) k = i; });
  const step = Math.max(1, Math.floor(times.length / 600));
  return times[Math.min(k * step, times.length - 1)] ?? null;
}

/** People still inside over the replay, about 60 samples. */
function insideSeries(r: Replay | null): number[] {
  if (!r) return [];
  const c = r.traj.counts();
  const step = Math.max(1, Math.floor(c.length / 60));
  return c.filter((_, i) => i % step === 0 || i === c.length - 1);
}
