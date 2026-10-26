/** Step 3 of the guided journey (route `/p/:projectId`): the tested plan as tabs, one idea each.
 * Overview (the verdict as a picture, key numbers, before vs after, the worst moment in 3D),
 * Replay (before / after / side by side on one clock, every scenario), Scenarios (cards and the
 * deeper checks), Fixes (the AI's tested changes to accept), Floors (one small plan per storey)
 * and Hand over (report, map, checklist, data). Every number comes from a run of a known venue
 * version and says what it is based on. */
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { Building2, Download, Flame, LayoutDashboard, Maximize2, MessageCircleQuestion, PlayCircle, RotateCcw, Send, ShieldCheck, ShieldQuestion, Swords, Waves, Wrench } from "lucide-react";
import type * as React from "react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useApplyFixes, usePlan, useProject, useRewind, useRun, useRunVenue, useSeedCheck, useSensitivity, useSession, useSessions, useSettings, useStartSession, useStartTogether, useStress, useTogether, useUndo, useVersions } from "@/api/queries";
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
import { FloorsTab } from "@/journey/plan/FloorsTab";
import { stressByAttack } from "@/journey/plan/gallery";
import { HandOver } from "@/journey/plan/HandOver";
import { Overview, type SessionMetrics } from "@/journey/plan/Overview";
import { FOCUS_FROM } from "@/scene/geom";
import { usePressure } from "@/journey/plan/pressure";
import { rangeVerdict } from "@/journey/plan/range";
import { RangePanel } from "@/journey/plan/RangePanel";
import { EvidencePanel } from "@/journey/plan/EvidencePanel";
import { SandboxesTab } from "@/journey/plan/SandboxesTab";
import { sandboxRows, scriptOutcomes } from "@/journey/plan/sandboxes";
import { ReplayStage } from "@/journey/plan/ReplayStage";
import { bestLine } from "@/journey/plan/rewind";
import { SavedActions } from "@/journey/plan/SavedActions";
import { FailureMapSlot } from "@/journey/plan/FailureMapSlot";
import { DeeperChecks, ScenarioCards, ScenarioCatalogue } from "@/journey/plan/ScenarioGallery";
import { ScenarioList } from "@/journey/plan/ScenarioViewer";
import { type ScenarioRow, scenarioMarkers, scenarioRows } from "@/journey/plan/scenarios";
import { SeedPanel } from "@/journey/plan/SeedPanel";
import { seedRangeLines as seedLinesOf } from "@/journey/plan/seeds";
import { planState } from "@/journey/plan/state";
import { rowOutcome, stressCounter } from "@/journey/plan/stress";
import { RealCaseCard } from "@/journey/RealCases";
import { realCaseOf, simulatedPeak } from "@/journey/realCases";
import { runBasisLabel } from "@/lib/evidence";
import { fmtClock, fmtNum, withoutRunIds } from "@/lib/format";
import { cn, UNDO_TOAST_ID } from "@/lib/utils";
import { displayNames, textHumanizer } from "@/lib/venueText";
import { FloorSwitch } from "@/panels/FloorSwitch";
import { Timeline } from "@/panels/Timeline";
import { type Thresholds, verdictOf } from "@/panels/verdict";
import type { Replay } from "@/replay/useReplay";
import { useReplay } from "@/replay/useReplay";
import { SceneRoot } from "@/scene/SceneRoot";
import { usePlayback } from "@/state/playback";
import { useUi } from "@/state/ui";
import { savedTestMode } from "@/journey/testModes";

export const PLAN_TABS = ["overview", "replay", "scenarios", "sandboxes", "fixes", "floors", "handover"] as const;
export type PlanTab = (typeof PLAN_TABS)[number];

/** Showtime's planning targets for "everyone out" when no hazard time is known (api settings
 * `target_evac_indoor_s` / `target_evac_outdoor_s`); shown as targets, never as results. */
const TARGET_INDOOR_S = 300;
const TARGET_OUTDOOR_S = 480;

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

/** When the run got everyone out, the time the last person left (null otherwise). */
function allOut(run: { result?: { metrics?: { agents_not_evacuated?: number | null; evac_time_max_s?: number | null } | null } | null } | undefined): number | null {
  const m = run?.result?.metrics;
  return m && m.agents_not_evacuated === 0 && m.evac_time_max_s != null ? m.evac_time_max_s : null;
}

export function YourPlanPage() {
  const { projectId = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const project = useProject(projectId);
  const selectedPlan = usePlan(projectId);
  const versions = useVersions(projectId);
  const settings = useSettings();
  const sessions = useSessions(projectId);
  const sessionId = params.get("session") ?? sessions.data?.[0]?.id ?? null;
  const session = useSession(sessionId);
  const summary = session.data?.summary ?? null;
  const ended = session.data?.status === "finished" || session.data?.status === "stopped";
  const view = useSessionStream(ended ? sessionId : null);
  const apply = useApplyFixes(projectId);
  const undo = useUndo(projectId);
  const start = useStartSession();
  const rewind = useRewind(sessionId);
  const stress = useStress(projectId);
  const seedCheck = useSeedCheck(sessionId);
  const sensitivity = useSensitivity(sessionId);
  // the tab lives in the URL (?tab=replay), so a link or a reload opens the same view; an
  // unknown tab (or Floors for a one-floor venue) is the Overview, for every hook below too
  const wanted = params.get("tab") ?? "overview";
  const multiFloor = (project.data?.version.venue.floors.length ?? 1) > 1;
  const tab: PlanTab = (PLAN_TABS as readonly string[]).includes(wanted) && (wanted !== "floors" || multiFloor)
    ? (wanted as PlanTab) : "overview";
  const go = (next: PlanTab) => setParams((prev) => {
    const q = new URLSearchParams(prev);
    if (next === "overview") q.delete("tab"); else q.set("tab", next);
    return q;
  }, { replace: true });
  // Replay tab: before, after, or both side by side on one clock; Overview: the worst moment
  const [mode, setMode] = useState<"before" | "after" | "split">("after");
  const [heroSide, setHeroSide] = useState<"before" | "after">("before");
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
  const activeReplayTab = tab === "replay";
  const beforeReplay = useReplay(beforeOk, tab === "overview" || activeReplayTab || tab === "floors");
  const afterReplay = useReplay(afterOk, true);
  const beforeVenue = useRunVenue(beforeOk);
  const afterVenue = useRunVenue(afterOk);
  const shownSide: "before" | "after" = hasAfter && mode !== "before" ? "after" : "before";
  const pickedRow = picked && picked.sid === sessionId ? picked.row : null;
  const pickedRun = useRun(pickedRow?.runId ?? null);
  const shown = pickedRow ? pickedRun.data : shownSide === "after" ? after.data : before.data;
  const shownId = usable(shown) ? shown!.id : null;
  const replay = useReplay(shownId, true);
  const shownVenue = useRunVenue(shownId);
  const split = mode === "split" && !pickedRow && hasAfter && !!beforeOk;
  const heroIsBefore = heroSide === "before" && !!beforeOk;
  const heroShown = heroIsBefore ? before.data : after.data ?? before.data;
  const heroReplay = heroIsBefore ? beforeReplay.data : afterReplay.data ?? beforeReplay.data;
  const heroVenue = heroIsBefore ? beforeVenue : afterOk ? afterVenue : beforeVenue;
  const pressure = usePressure(shownId, activeReplayTab);
  const turb = turbulence && !split && pressure.data ? pressure.data : null;
  // one clock: the replay the open tab shows drives it; the worst moment starts just before its peak
  const clockReplay = tab === "overview" ? heroReplay : activeReplayTab ? replay.data : null;
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
  const compareReplay = activeReplayTab && split ? beforeReplay.data : null;
  useEffect(() => {
    if (!clockReplay) return;
    const pb = usePlayback.getState();
    pb.setDuration(Math.max(clockReplay.traj.duration, compareReplay?.traj.duration ?? 0));
    const peak = tab === "overview" ? peakMoment(clockReplay) : null;
    pb.setT(peak != null ? Math.max(0, peak - 12) : 0);
    pb.play();
  }, [clockReplay, compareReplay, tab]);

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
  const kept = useMemo<Fix[]>(() => {
    const fixes = summary?.fixes ?? [];
    return (summary?.accepted_fixes ?? []).map((id) => fixes.find((f) => f.fix_id === id)).filter((f): f is Fix => !!f);
  }, [summary]);
  const deps = useMemo(() => fixDependencies(kept), [kept]);
  const rows = useMemo(() => scenarioRows(view.nodes, view.runs, summary?.attacks ?? [], summary?.fixes ?? [], human),
    [view.nodes, view.runs, summary, human]);

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
  const testAgain = () => start.mutate({ project_id: p.id, config: savedTestMode().config }, {
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
  const th: Thresholds = { warn: Number(eff.density_warn_ppm2 ?? 3.5), danger: Number(eff.density_danger_ppm2 ?? 5), dangerMinS: 5 };
  const testedHash = versions.data?.find((v) => v.version === session.data?.venue_version)?.plan_hash;
  const { state, record } = planState({ currentHash: p.version.plan_hash, testedHash, kept: kept.length,
    applied: summary?.applied, fixedHash: after.data?.evidence?.plan_hash });
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

  const verdictOut = hasAfter ? after.data : usable(before.data) ? before.data : undefined;
  const verdictRun = verdictOut?.result ?? null;
  const verdict = verdictOf(verdictRun, th, label);
  const basis = runBasisLabel(verdictRun);
  const cd = summary?.countdown;
  const cdBasis = [(cd?.status === "ok" || cd?.status === "too_late") ? cd.hazard_explanation : "",
    withoutRunIds(cd?.rset_source) ? t("yourplan.cd_from", { source: withoutRunIds(cd?.rset_source) }) : t("yourplan.cd_source")].filter(Boolean).join(" · ");
  const worst = summary?.attacks?.find((a) => a.attack_id === summary.worst_attack_id);
  const judge = summary?.judge_text ? `${human(summary.judge_text)}${summary.numbers_checked ? ` ${t("yourplan.numbers_checked")}` : ""}` : null;
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
  /** a run from outside the session (a sweep result, the failure map) plays in the replay */
  const playRun = (runId: string, title: string) => {
    pick({ key: `run:${runId}`, kind: "attack", title, runId, outcome: "unknown", evacS: null, peak: null, inside: null, children: [] });
    go("replay");
  };
  const deciding = state === "pending" && kept.length > 0;
  const primary = deciding || state === "accepted_subset" ? null : state === "stale" ? "test" : "report";
  const multi = venue.floors.length > 1;
  const pending = deciding ? selected.size : 0;
  const reportUrl = api.url(`/sessions/${sessionId}/report`);

  const peakAt = peakMoment(heroReplay);
  const heroBasis = heroShown ? runBasisLabel(heroShown.result) : t("evidence.basis.unknown");
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
  const sides = [{ id: "before", label: t("yourplan.before") }, { id: "after", label: t("yourplan.after") }];

  const hero = (
    <ReplayStage label={t("plan.worst_moment_region")} className="h-[340px] lg:h-full lg:min-h-[340px]"
                 main={{ venue: heroVenue.data ?? venue, replay: heroReplay ?? null }} markers={markersFor(null, heroSide)} basis={heroBasis}
                 chip={<span className="inline-flex items-center gap-1.5 rounded-full bg-ink px-3 py-1 text-xs font-semibold text-plan shadow-sm">
                   <Flame className="size-3.5 text-orange" aria-hidden />{heroSide === "before" ? t("plan.worst_moment", { at: fmtClock(peakAt ?? 0) }) : t("plan.with_your_fixes")}</span>}
                 top={bothSides ? segmented(sides, heroSide, (v) => setHeroSide(v as "before" | "after"), t("yourplan.before_after")) : undefined}
                 corner={<Button size="sm" className="shadow-sm" onClick={() => go("replay")}><Maximize2 />{t("plan.open_replay")}</Button>} />
  );

  const next = deciding ? (
    <NextCard icon={<Wrench />} tone="bg-signal-soft text-signal" title={t(kept.length === 1 ? "plan.next_fix" : "plan.next_fixes", { n: kept.length })} body={t("plan.next_fixes_body")}
              action={<Button variant="primary" size="lg" onClick={() => go("fixes")}><Wrench />{t("plan.review_fixes")}</Button>} />
  ) : state === "stale" || state === "accepted_subset" ? (
    <NextCard icon={<RotateCcw />} tone="bg-caution-soft text-caution-strong" title={t(state === "stale" ? "plan.next_stale" : "plan.next_subset")} body={t("plan.next_test_body")}
              action={<Button variant="primary" size="lg" onClick={testAgain} disabled={start.isPending}><RotateCcw />{t("yourplan.test_again")}</Button>} />
  ) : (
    <NextCard icon={<Send />} tone="bg-egress-soft text-egress-strong" title={t("plan.next_handover")} body={t("plan.next_handover_body")}
              action={<Button variant="primary" size="lg" onClick={() => go("handover")}><Send />{t("plan.tab_handover")}</Button>} />
  );

  const rewindRec = rewind.data ?? null;
  const stressRec = stress.data ?? null;
  const seedLines = seedLinesOf(seedCheck.data);
  const checkStatus = {
    rewind: !rewindRec ? t("plan.not_run") : rewindRec.status === "running" ? t("plan.running") : rewindRec.status === "done" ? bestLine(rewindRec) : t("plan.not_run"),
    stress: !stressRec ? t("plan.not_run") : stressRec.status === "running" ? stressCounter(stressRec).text
      : t("plan.stress_done", { k: stressRec.rows.filter((r) => rowOutcome(r) === "breaks").length, n: stressRec.rows.length }),
    seeds: seedLines?.[0] ?? (seedCheck.data?.status === "running" ? t("plan.running") : t("plan.not_run")),
    range: !sensitivity.data || sensitivity.data.status === "none" ? t("plan.not_run") : rangeVerdict(sensitivity.data).text,
  };
  const tabs: { id: PlanTab; icon: React.ReactNode; label: string; badge?: number }[] = [
    { id: "overview", icon: <LayoutDashboard />, label: t("plan.tab_overview") },
    { id: "replay", icon: <PlayCircle />, label: t("plan.tab_replay") },
    { id: "scenarios", icon: <Swords />, label: t("plan.tab_scenarios"), badge: rows.filter((r) => r.kind === "attack" && !r.key.includes(":current:")).length || undefined },
    { id: "sandboxes", icon: <ShieldCheck />, label: t("plan.tab_sandboxes"), badge: sandboxRows(view).rows.length || undefined },
    { id: "fixes", icon: <Wrench />, label: t("plan.tab_fixes"), badge: pending || undefined },
    ...(multi ? [{ id: "floors" as const, icon: <Building2 />, label: t("plan.tab_floors"), badge: venue.floors.length }] : []),
    { id: "handover", icon: <Send />, label: t("plan.tab_handover") },
  ];
  const activeTab = tabs.some((x) => x.id === tab) ? tab : "overview";

  return (
    <JourneyShell step="plan" projectId={p.id} title={p.name} back={{ to: "/", label: t("journey.home") }}>
      <main id="main" className="mx-auto w-full min-w-0 max-w-6xl space-y-4 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight">{p.name}</h1>
            <p className="text-sm text-muted tabular">{t("yourplan.version", { n: p.current_version })}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button asChild variant={primary === "report" ? "primary" : "secondary"}>
              <a href={reportUrl} target="_blank" rel="noreferrer"><Download />{t("yourplan.report")}</a>
            </Button>
            <Button variant={primary === "test" ? "primary" : "secondary"} onClick={testAgain} disabled={start.isPending}><RotateCcw />{t("yourplan.test_again")}</Button>
          </div>
        </div>

        {state === "stale" && (
          <div role="status" className="flex flex-wrap items-center gap-3 rounded-[10px] border border-caution/40 bg-caution-soft p-3 text-sm">
            <ShieldQuestion className="size-5 shrink-0 text-caution" />
            <span className="min-w-0 flex-1">{t("yourplan.stale")}</span>
          </div>
        )}
        {status === "stopped" && <p role="status" className="rounded-[10px] border border-caution/40 bg-caution-soft p-3 text-sm">{t("yourplan.partial", { reason: summary?.stopped_reason ?? "" })}</p>}

        <Tabs value={activeTab} onValueChange={(v) => go(v as PlanTab)} className="space-y-4">
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
            <Overview level={verdictRun ? verdict.level : "unknown"} headline={verdictRun ? verdict.headline : t("yourplan.no_result")}
                      evaluation={subsetRun ? subsetRecord?.together?.evaluation : summary?.evaluation}
                      worst={worst ? human(worst.title) : null} fixes={hasAfter ? (state === "accepted_subset" ? record?.fix_ids.length ?? kept.length : kept.length) : 0}
                      reasons={verdict.reasons} run={verdictRun} stoodIn={summary?.stood_in}
                      sandboxes={{ runs: sandboxRows(view).rows.length, scripts: scriptOutcomes(view, summary?.attacks ?? []).length, onOpen: () => go("sandboxes") }}
                      score={{ attacks: (summary?.scoreboard ?? []).reduce((n, r) => n + r.attacks, 0) || (summary?.attacks?.length ?? 0),
                               breaks: (summary?.scoreboard ?? []).reduce((n, r) => n + r.breaks, 0), fixes: kept.length }} basis={basis} countdown={cd} countdownBasis={cdBasis} th={th}
                      targetS={venue.mode === "indoor" ? TARGET_INDOOR_S : TARGET_OUTDOOR_S}
                      before={summary?.before as SessionMetrics | undefined}
                      after={subsetRun ? metricsOf(after.data) : summary?.after as SessionMetrics | undefined}
                      insideSeries={insideSeries(afterReplay.data ?? null)} hero={hero} next={next}
                      summary={{ judge, reasons: summary?.evaluation?.reasons ?? [], recommendations: (summary?.recommendations ?? []).map(human) }}
                      realCase={caseCard ? <RealCaseCard card={caseCard} peak={simulatedPeak(caseRun.data?.result, venue, label)} /> : undefined} />
          </TabsContent>

          <TabsContent value="replay" className="animate-tab-in">
            <div className="grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
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
                               : bothSides ? segmented([...sides, { id: "split", label: t("plan.side_by_side") }], mode, (v) => setMode(v as "before" | "after" | "split"), t("yourplan.before_after"))
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
          </TabsContent>

          <TabsContent value="scenarios" className="animate-tab-in space-y-6">
            <ScenarioCards rows={rows} attacks={summary?.attacks ?? []} name={label} stress={stressByAttack(stressRec)} danger={th.danger}
                           onPlay={(row) => { pick(row); go("replay"); }} />
            <EvidencePanel attacks={summary?.attacks ?? []} human={human} />
            <FailureMapSlot projectId={p.id} sessionId={sessionId} onSelectRun={playRun}
                            hasArchive={session.data?.status === "running" || session.data?.status === "queued" || !session.data?.summary || "archive" in session.data.summary} />
            <ScenarioCatalogue projectId={p.id} version={p.current_version} onPlay={playRun} danger={th.danger} />
            <DeeperChecks status={checkStatus} panels={{
              seeds: <SeedPanel sessionId={sessionId} human={human} />,
              range: <RangePanel sessionId={sessionId} />,
            }} />
          </TabsContent>

          <TabsContent value="sandboxes" className="animate-tab-in">
            <SandboxesTab view={view} attacks={summary?.attacks ?? []} sessionId={sessionId} projectId={p.id}
                          worstTitle={worst ? human(worst.title) : null} human={human} />
          </TabsContent>

          <TabsContent value="fixes" className="animate-tab-in">
            <FixChooser kept={kept} selected={selected} deps={deps} onToggle={toggle} nodes={view.nodes} loading={!view.ended}
                        venue={venue} state={state} record={record} attackTitle={attackTitle} name={label} human={human}
                        onAccept={accept} accepting={apply.isPending} onTestAgain={testAgain} testing={start.isPending}
                        together={togetherCheck.data?.record?.plan_hash === record?.plan_hash ? togetherCheck.data?.record?.together : record?.together}
                        onTogether={() => startTogether.mutate(undefined, { onError: (e) => toast.error(e.message) })} togetherBusy={startTogether.isPending} />
          </TabsContent>

          {multi && (
            <TabsContent value="floors" className="animate-tab-in">
              <FloorsTab venue={venue} traj={(afterReplay.data ?? beforeReplay.data)?.traj ?? null}
                         allOutS={allOut(afterReplay.data ? after.data : before.data)}
                         onWatch={(floorId) => { useUi.getState().setFloorView(floorId); go("replay"); }} />
            </TabsContent>
          )}

          <TabsContent value="handover" className="animate-tab-in">
            <HandOver sessionId={sessionId} projectId={p.id} venue={venue} projectName={p.name} onTestAgain={testAgain} testing={start.isPending}>
              <CostCard cost={summary?.cost} tokens={session.data?.tokens ?? 0} costUsd={session.data?.cost_usd ?? 0} />
            </HandOver>
          </TabsContent>
        </Tabs>

        <Button asChild variant="link" className="hidden xl:inline-flex"><Link to={`/p/${p.id}/expert`}>{t("journey.expert")}</Link></Button>
      </main>
    </JourneyShell>
  );
}

function NextCard({ icon, tone, title, body, action }: { icon: React.ReactNode; tone: string; title: string; body: string; action: React.ReactNode }) {
  return (
    <section aria-labelledby="next-h" className="flex h-full flex-col gap-3 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
      <div className="flex items-start gap-3">
        <span className={cn("grid size-11 shrink-0 place-items-center rounded-[12px] [&_svg]:size-5", tone)}>{icon}</span>
        <div className="min-w-0">
          <h2 id="next-h" className="text-lg font-semibold leading-tight">{title}</h2>
          <p className="text-sm text-muted">{body}</p>
        </div>
      </div>
      <div className="mt-auto">{action}</div>
    </section>
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
