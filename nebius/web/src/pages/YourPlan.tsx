/** Step 3 of the guided journey (route `/p/:projectId`), top to bottom: the verdict and what the
 * tests show, the AI's tested changes to choose from, the before/after replay, how the plan was
 * made, a box to ask or change anything, and the next steps. Every number comes from a run of a
 * known venue version and says what it is based on. */
import { ExternalLink, RotateCcw, ShieldQuestion } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useApplyFixes, usePlan, useProject, useRun, useRunVenue, useSession, useSessions, useSettings, useStartSession, useUndo, useVersions } from "@/api/queries";
import type { Countdown, Fix, RunOut } from "@/api/types";
import { useSessionStream } from "@/api/useSessionStream";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton, Spinner } from "@/components/ui/misc";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";
import { AskAnything } from "@/journey/AskAnything";
import type { ProposalPreview } from "@/journey/AskChange";
import { JourneyShell } from "@/journey/JourneyShell";
import { CostCard } from "@/journey/plan/CostCard";
import { FixChooser } from "@/journey/plan/FixChooser";
import { acceptBody, evacValue, fixDependencies, toggleFix } from "@/journey/plan/fixes";
import { NextActions } from "@/journey/plan/NextActions";
import { RewindPanel } from "@/journey/plan/RewindPanel";
import { SavedActions } from "@/journey/plan/SavedActions";
import { planState } from "@/journey/plan/state";
import { StressPanel } from "@/journey/plan/StressPanel";
import { type KeyNumber, VerdictBanner } from "@/journey/plan/VerdictBanner";
import { runBasisLabel, runOutcome } from "@/lib/evidence";
import { fmtDuration, fmtHM, fmtInt, fmtNum } from "@/lib/format";
import { cn } from "@/lib/utils";
import { displayNames, textHumanizer } from "@/lib/venueText";
import { type Thresholds, verdictOf } from "@/panels/verdict";
import { useReplay } from "@/replay/useReplay";
import { SceneRoot } from "@/scene/SceneRoot";
import { usePlayback } from "@/state/playback";
import { useUi } from "@/state/ui";
import { QUICK_TEST } from "./CheckVenue";

export function countdownText(c: Countdown | null | undefined): string {
  if (!c) return t("yourplan.cd_unknown");
  if (c.status === "ok") return c.t_latest_iso ? t("yourplan.cd_by", { time: fmtHM(c.t_latest_iso) }) : t("yourplan.cd_within", { d: fmtDuration(c.t_latest_s) });
  if (c.status === "too_late") return t("yourplan.cd_too_late");
  if (c.status === "no_hazard") return t("yourplan.cd_no_hazard");
  return t("yourplan.cd_unknown");
}

const usable = (r: RunOut | undefined) => !!r && (r.status === "ok" || r.status === "partial");
const noop = () => {};

export function YourPlanPage() {
  const { projectId = "" } = useParams();
  const [params] = useSearchParams();
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
  const [side, setSide] = useState<"before" | "after">("after");
  const [proposal, setProposal] = useState<ProposalPreview | null>(null);
  // the organizer's choice of kept fixes, per session (default: all of them)
  const [choice, setChoice] = useState<{ sid: string | null; ids: Set<string> } | null>(null);

  useEffect(() => { useUi.getState().resetForProject(); usePlayback.getState().reset(); }, [projectId]);

  const afterId = summary?.final_run_id ?? null;
  const worstNode = summary?.worst_attack_id ? view.nodes[`atk:${summary.worst_attack_id}`]?.run_id : undefined;
  const beforeId = view.nodes["final:before"]?.run_id ?? worstNode ?? summary?.baseline_run_id ?? null;
  const after = useRun(afterId);
  const before = useRun(beforeId);
  const hasAfter = usable(after.data);
  const shownSide = hasAfter && side === "after" ? "after" : "before";
  const shown = shownSide === "after" ? after.data : before.data;
  const shownId = usable(shown) ? shown!.id : null;
  const replay = useReplay(shownId, true);
  const shownVenue = useRunVenue(shownId);
  useEffect(() => {
    if (!replay.data) return;
    usePlayback.getState().setDuration(replay.data.traj.duration);
    usePlayback.getState().setT(0);
    usePlayback.getState().play();
  }, [replay.data]);

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
        <main className="mx-auto w-full max-w-6xl space-y-4 p-4"><Skeleton className="h-24" /><div className="grid gap-3 sm:grid-cols-3"><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /></div><Skeleton className="h-80" /></main>
      </JourneyShell>
    );
  }

  const label = (id: string) => names.get(id) ?? id;
  const testAgain = () => start.mutate({ project_id: p.id, config: QUICK_TEST }, {
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
          <div className="relative h-[50vh] overflow-hidden rounded-[10px] border border-border">
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
      description: r.applied && !r.applied.tested_together ? t("yourplan.subset_note") : undefined,
      action: { label: t("common.undo"), onClick: () => undo.mutate() },
    }),
    onError: (e) => toast.error(e.message, { description: (e as { hint?: string | null }).hint ?? undefined }),
  });

  const verdictOut = hasAfter ? after.data : usable(before.data) ? before.data : undefined;
  const verdictRun = verdictOut?.result ?? null;
  const verdict = verdictOf(verdictRun, th, label);
  const basis = runBasisLabel(verdictRun);
  const m = verdictRun?.metrics;
  const extra = (m?.extra ?? {}) as Record<string, number | null | undefined>;
  const cd = summary?.countdown;
  const numbers: KeyNumber[] = [
    { label: t("yourplan.n_evac"), value: m ? evacValue({ evac_time_p95_s: m.evac_time_p95_s, evac_time_estimate_s: extra.rset_extrapolated_s }) : "–",
      detail: m ? t("yourplan.n_inside", { n: fmtInt(m.agents_not_evacuated) }) : undefined, basis },
    { label: t("yourplan.n_peak"), value: m ? `${fmtNum(m.peak_density_ppm2, 1)} ${t("yourplan.per_m2")}` : "–", basis },
    { label: t("yourplan.n_start"), value: countdownText(cd),
      basis: [(cd?.status === "ok" || cd?.status === "too_late") ? cd.hazard_explanation : "",
        cd?.rset_source ? t("yourplan.cd_from", { source: cd.rset_source }) : t("yourplan.cd_source")].filter(Boolean).join(" · ") },
  ];
  const worst = summary?.attacks?.find((a) => a.attack_id === summary.worst_attack_id);
  const subset = state === "accepted_subset" && hasAfter
    ? ` ${t("yourplan.under_subset", { n: kept.length, k: record?.fix_ids.length ?? 0 })}` : "";
  const under = `${worst ? t("yourplan.under", { attack: human(worst.title) }) : t("yourplan.under_baseline")}${hasAfter ? ` ${t("yourplan.with_changes")}` : ""}${subset}`;
  const judge = summary?.judge_text ? `${human(summary.judge_text)}${summary.numbers_checked ? ` ${t("yourplan.numbers_checked")}` : ""}` : null;
  const attackTitle = (id: string) => summary?.attacks?.find((a) => a.attack_id === id)?.title ?? id;
  const risks = (summary?.attacks ?? []).slice(0, 3);
  const deciding = state === "pending" && kept.length > 0;
  const primary = deciding || state === "accepted_subset" ? null : state === "stale" ? "test" : "report";
  const previewing = !!proposal;

  return (
    <JourneyShell step="plan" projectId={p.id} title={p.name} back={{ to: "/", label: t("journey.home") }}>
      <main id="main" className="mx-auto w-full max-w-6xl space-y-4 p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">{p.name}</h1>
          <span className="text-sm text-muted tabular">{t("yourplan.version", { n: p.current_version })}</span>
        </div>

        {state === "stale" && (
          <div role="status" className="flex flex-wrap items-center gap-3 rounded-[10px] border border-caution/40 bg-caution-soft p-3 text-sm">
            <ShieldQuestion className="size-5 shrink-0 text-caution" />
            <span className="min-w-0 flex-1">{t("yourplan.stale")}</span>
            <Button onClick={testAgain} disabled={start.isPending}><RotateCcw />{t("yourplan.test_again")}</Button>
          </div>
        )}
        {status === "stopped" && <p role="status" className="rounded-[10px] border border-caution/40 bg-caution-soft p-3 text-sm">{t("yourplan.partial", { reason: summary?.stopped_reason ?? "" })}</p>}

        <VerdictBanner level={verdictRun ? verdict.level : "unknown"} headline={verdictRun ? verdict.headline : t("yourplan.no_result")}
                       under={under} reasons={verdict.reasons} evaluation={summary?.evaluation} judge={judge} numbers={numbers} />

        <FixChooser kept={kept} selected={selected} deps={deps} onToggle={toggle} nodes={view.nodes} loading={!view.ended}
                    venue={venue} state={state} record={record} attackTitle={attackTitle} name={label} human={human}
                    onAccept={accept} accepting={apply.isPending} onTestAgain={testAgain} testing={start.isPending} />

        <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
          <section aria-label={t("yourplan.replay")} className="relative h-[50vh] min-h-80 overflow-hidden rounded-[10px] border border-border">
            <SceneRoot venue={previewing ? proposal.venue : shownVenue.data ?? venue} replay={previewing ? null : replay.data ?? null} hotspots={[]} marshals={[]}
                       editable={false} resetNonce={0} quality="low" highlights={previewing ? proposal.changes : undefined}
                       onExitClick={noop} onObjectClick={noop} onFloorClick={noop} onFloorDoubleClick={noop} onMove={noop} onHotspot={noop} />
            {!previewing && hasAfter && usable(before.data) && (
              <div role="group" aria-label={t("yourplan.before_after")} className="absolute left-1/2 top-3 flex -translate-x-1/2 rounded-[8px] bg-surface p-0.5 shadow-[var(--shadow-float)]">
                {(["before", "after"] as const).map((s) => (
                  <button key={s} type="button" aria-pressed={shownSide === s} onClick={() => setSide(s)}
                          className={cn("min-h-11 rounded-[6px] px-4 text-sm font-medium", shownSide === s ? "bg-signal text-signal-ink" : "text-muted hover:text-ink")}>
                    {t(`yourplan.${s}`)}
                  </button>
                ))}
              </div>
            )}
            {!previewing && <span className="pointer-events-none absolute bottom-3 left-3 rounded-full bg-surface/95 px-3 py-1 text-xs shadow-sm">{shown ? runBasisLabel(shown.result) : t("evidence.basis.unknown")}</span>}
          </section>

          <div className="space-y-4">
            <section aria-labelledby="risks-h" className="space-y-2 rounded-[10px] border border-border bg-surface p-4">
              <h2 id="risks-h" className="font-semibold">{t("yourplan.risks")}</h2>
              {risks.length === 0 ? <p className="text-sm text-muted">{t("yourplan.no_risks")}</p> : (
                <ul className="space-y-2">
                  {risks.map((a) => {
                    const node = view.nodes[`atk:${a.attack_id}`];
                    const r = node ? view.runs[node.run_id] : undefined;
                    const outcome = r ? runOutcome(r) : null;
                    return (
                      <li key={a.attack_id} className="rounded-[8px] border border-border p-2.5 text-sm">
                        <div className="flex items-start justify-between gap-2">
                          <p className="font-medium">{human(a.title)}</p>
                          {outcome && (outcome === "break" ? <Badge tone="danger">{t("work.breaks")}</Badge> : outcome === "holds" ? <Badge tone="egress">{t("work.holds")}</Badge> : <Badge tone="neutral">{t(outcome === "preview" ? "work.preview" : "work.unknown")}</Badge>)}
                        </div>
                        {a.inspired_by?.source_url && (
                          <a href={a.inspired_by.source_url} target="_blank" rel="noreferrer" className="mt-1 flex min-h-11 items-center gap-1 text-xs text-signal hover:underline">
                            <ExternalLink className="size-3" />{t("work.inspired_by", { what: `${a.inspired_by.incident}${a.inspired_by.year ? ` (${a.inspired_by.year})` : ""}` })}
                          </a>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
            {selectedPlan.data && <SavedActions actions={selectedPlan.data.plan.actions} version={selectedPlan.data.version} projectId={p.id} name={label} />}
          </div>
        </div>

        <div className="grid items-start gap-4 lg:grid-cols-2">
          <CostCard cost={summary?.cost} tokens={session.data?.tokens ?? 0} costUsd={session.data?.cost_usd ?? 0} />
          <section aria-labelledby="ask-h" className="space-y-2 rounded-[var(--radius-panel)] border border-border bg-surface p-4 shadow-sm">
            <h2 id="ask-h" className="font-semibold">{t("ask.label")}</h2>
            <AskAnything project={p} context="plan" sessionId={sessionId} onPreview={setProposal} className="max-w-none" />
          </section>
        </div>

        <div className="grid items-start gap-4 lg:grid-cols-2"><RewindPanel sessionId={sessionId} worstTitle={worst ? human(worst.title) : null} /><StressPanel projectId={p.id} hasTest /></div>

        <NextActions reportUrl={api.url(`/sessions/${sessionId}/report`)} checklistUrl={api.url(`/sessions/${sessionId}/checklist`)}
                     projectId={p.id} onTestAgain={testAgain} testing={start.isPending} primary={primary} />
        <Button asChild variant="link" className="hidden xl:inline-flex"><Link to={`/p/${p.id}/expert`}>{t("journey.expert")}</Link></Button>
      </main>
    </JourneyShell>
  );
}
