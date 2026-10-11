/** Step 3 of the guided journey (route `/p/:projectId`): is it safe, what did the AI change,
 * and what to do next. Every number comes from a simulation run of a known venue version. */
import { Check, Download, ExternalLink, Hammer, Lock, Pencil, RotateCcw, ShieldAlert, ShieldCheck, ShieldQuestion, Swords, Workflow } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useApplySession, useProject, useRun, useRunVenue, useSession, useSessions, useSettings, useStartSession, useUndo, useVersions } from "@/api/queries";
import type { Countdown, Fix, PatchOpIn, RunOut, RunResult } from "@/api/types";
import { useSessionStream } from "@/api/useSessionStream";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton, Spinner } from "@/components/ui/misc";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";
import { JourneyShell } from "@/journey/JourneyShell";
import { lockConflicts } from "@/lib/annotations";
import { planFreshness } from "@/lib/evidence";
import { fmtDuration, fmtHM, fmtInt, fmtNum } from "@/lib/format";
import { cn } from "@/lib/utils";
import { displayNames, textHumanizer } from "@/lib/venueText";
import { describeEvent, describeOp } from "@/panels/describe";
import { type Thresholds, verdictOf } from "@/panels/verdict";
import { useReplay } from "@/replay/useReplay";
import { SceneRoot } from "@/scene/SceneRoot";
import { usePlayback } from "@/state/playback";
import { useUi } from "@/state/ui";
import { QUICK_TEST } from "./CheckVenue";

const CONSTRUCTION = new Set(["add_exit", "add_obstacle", "add_barrier_line"]);

/** Where a number comes from, in plain words (never "Tier"). */
export function sourceTag(run: RunOut | undefined | null): string {
  if (!run) return t("yourplan.src_none");
  if (run.status === "failed" || run.status === "timeout" || run.status === "cancelled") return t("yourplan.src_failed");
  if (run.tier === 3) return run.status === "partial" ? t("yourplan.src_partial") : t("yourplan.src_full");
  if (run.tier === 2) return t("yourplan.src_quick");
  return t("yourplan.src_estimate");
}

export function countdownText(c: Countdown | null | undefined): string {
  if (!c) return t("yourplan.cd_unknown");
  if (c.status === "ok") return c.t_latest_iso ? t("yourplan.cd_by", { time: fmtHM(c.t_latest_iso) }) : t("yourplan.cd_within", { d: fmtDuration(c.t_latest_s) });
  if (c.status === "too_late") return t("yourplan.cd_too_late");
  if (c.status === "no_hazard") return t("yourplan.cd_no_hazard");
  return t("yourplan.cd_unknown");
}

function evacText(r: RunResult | null | undefined): string {
  const m = r?.metrics;
  if (!m) return "–";
  if (m.evac_time_p95_s != null) return fmtDuration(m.evac_time_p95_s);
  if ((m.agents_not_evacuated ?? 0) > 0) return t("yourplan.still_inside", { n: fmtInt(m.agents_not_evacuated) });
  return "–";
}

const usable = (r: RunOut | undefined) => !!r && (r.status === "ok" || r.status === "partial");

export function YourPlanPage() {
  const { projectId = "" } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const project = useProject(projectId);
  const versions = useVersions(projectId);
  const settings = useSettings();
  const sessions = useSessions(projectId);
  const sessionId = params.get("session") ?? sessions.data?.[0]?.id ?? null;
  const session = useSession(sessionId);
  const summary = session.data?.summary ?? null;
  const ended = session.data?.status === "finished" || session.data?.status === "stopped";
  const view = useSessionStream(ended ? sessionId : null);
  const apply = useApplySession(projectId);
  const undo = useUndo(projectId);
  const start = useStartSession();
  const [side, setSide] = useState<"before" | "after">("after");

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
  const names = useMemo(() => (venue ? displayNames(venue) : new Map<string, string>()), [venue]);
  const human = useMemo(() => (venue ? textHumanizer(venue) : (s: string) => s), [venue]);

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

  const eff = settings.data?.effective ?? {};
  const th: Thresholds = { warn: Number(eff.density_warn_ppm2 ?? 3.5), danger: Number(eff.density_danger_ppm2 ?? 5), dangerMinS: 5 };
  const testedHash = versions.data?.find((v) => v.version === session.data?.venue_version)?.venue_hash;
  const freshness = planFreshness({ currentHash: p.version.venue_hash, testedHash, fixedHash: after.data?.result?.venue_hash });
  const kept: Fix[] = (summary?.fixes ?? []).filter((f) => summary?.accepted_fixes?.includes(f.fix_id));
  const conflicts = lockConflicts(venue, kept.flatMap((f) => (f.patch?.ops ?? []) as PatchOpIn[]));
  const verdictRun = (hasAfter ? after.data : usable(before.data) ? before.data : null)?.result ?? null;
  const verdict = verdictOf(verdictRun, th, (id) => names.get(id) ?? id);
  const testAgain = () => start.mutate({ project_id: p.id, config: QUICK_TEST }, {
    onSuccess: (s) => navigate(`/p/${p.id}/work?session=${s.id}&live=1`),
    onError: (e) => toast.error(e.message),
  });
  const accept = () => sessionId && apply.mutate(sessionId, {
    onSuccess: (r) => toast.success(t("yourplan.accepted", { n: r.version.version }), { action: { label: t("common.undo"), onClick: () => undo.mutate() } }),
    onError: (e) => toast.error(e.message),
  });
  const canAccept = freshness === "current_before" && kept.length > 0 && conflicts.length === 0 && !!summary;
  const acceptFirst = freshness === "current_before" && kept.length > 0;

  // --- untested, running or failed ---------------------------------------------------
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
                       onExitClick={() => {}} onObjectClick={() => {}} onFloorClick={() => {}} onFloorDoubleClick={() => {}} onMove={() => {}} onHotspot={() => {}} />
          </div>
        </main>
      </JourneyShell>
    );
  }

  // --- tested ------------------------------------------------------------------------
  const tone = verdict.level === "fails" ? "border-danger/35 bg-danger-soft" : verdict.level === "at_risk" ? "border-caution/35 bg-caution-soft"
    : verdict.level === "holds" ? "border-egress/35 bg-egress-soft" : "border-border bg-surface-2";
  const icon = verdict.level === "fails" ? <ShieldAlert className="text-danger" /> : verdict.level === "holds" ? <ShieldCheck className="text-egress" /> : <ShieldQuestion className="text-caution" />;
  const reportUrl = api.url(`/sessions/${sessionId}/report`);
  const worst = summary?.attacks?.find((a) => a.attack_id === summary.worst_attack_id);
  const risks = (summary?.attacks ?? []).slice(0, 3);
  const numbers: { label: string; value: string; source: string }[] = [
    { label: t("yourplan.n_evac"), value: evacText(verdictRun), source: sourceTag(hasAfter ? after.data : before.data) },
    { label: t("yourplan.n_peak"), value: verdictRun?.metrics ? `${fmtNum(verdictRun.metrics.peak_density_ppm2, 1)} ${t("yourplan.per_m2")}` : "–", source: sourceTag(hasAfter ? after.data : before.data) },
    { label: t("yourplan.n_start"), value: countdownText(summary?.countdown), source: (summary?.countdown?.status === "ok" || summary?.countdown?.status === "too_late") && summary.countdown.hazard_explanation
      ? summary.countdown.hazard_explanation : t("yourplan.cd_source") },
  ];

  return (
    <JourneyShell step="plan" projectId={p.id} title={p.name} back={{ to: "/", label: t("journey.home") }}>
      <main id="main" className="mx-auto w-full max-w-6xl space-y-4 p-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">{p.name}</h1>
          <span className="text-sm text-muted tabular">{t("yourplan.version", { n: p.current_version })}</span>
        </div>

        {freshness === "stale" && (
          <div role="status" className="flex flex-wrap items-center gap-3 rounded-[10px] border border-caution/40 bg-caution-soft p-3 text-sm">
            <ShieldQuestion className="size-5 shrink-0 text-caution" />
            <span className="min-w-0 flex-1">{t("yourplan.stale")}</span>
            <Button onClick={testAgain} disabled={start.isPending}><RotateCcw />{t("yourplan.test_again")}</Button>
          </div>
        )}
        {status === "stopped" && <p role="status" className="rounded-[10px] border border-caution/40 bg-caution-soft p-3 text-sm">{t("yourplan.partial", { reason: summary?.stopped_reason ?? "" })}</p>}

        <section aria-label={t("yourplan.verdict")} className={cn("flex flex-wrap items-start gap-3 rounded-[12px] border p-4", tone)}>
          <span className="mt-0.5 [&_svg]:size-7">{icon}</span>
          <div className="min-w-0 flex-1">
            <p className="text-xl font-semibold leading-tight">{verdictRun ? verdict.headline : t("yourplan.no_result")}</p>
            <p className="mt-1 max-w-prose text-base">
              {worst ? t("yourplan.under", { attack: human(worst.title) }) : t("yourplan.under_baseline")}
              {hasAfter ? ` ${t("yourplan.with_changes")}` : ""}
            </p>
            {verdict.reasons.length > 0 && <ul className="mt-1 list-disc pl-5 text-sm">{verdict.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
            {summary?.judge_text && <p className="mt-2 max-w-prose text-sm text-muted">{human(summary.judge_text)}{(summary as { numbers_checked?: boolean }).numbers_checked ? ` ${t("yourplan.numbers_checked")}` : ""}</p>}
          </div>
          <Button asChild variant={acceptFirst ? "secondary" : "primary"} size="lg">
            <a href={reportUrl} target="_blank" rel="noreferrer"><Download />{t("yourplan.report")}</a>
          </Button>
        </section>

        <ul className="grid gap-3 sm:grid-cols-3">
          {numbers.map((n) => (
            <li key={n.label} className="rounded-[10px] border border-border bg-surface p-3">
              <p className="text-sm text-muted">{n.label}</p>
              <p className="mt-0.5 text-xl font-semibold tabular">{n.value}</p>
              <p className="mt-0.5 text-xs text-muted">{n.source}</p>
            </li>
          ))}
        </ul>

        <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
          <section aria-label={t("yourplan.replay")} className="relative h-[50vh] min-h-80 overflow-hidden rounded-[10px] border border-border">
            <SceneRoot venue={shownVenue.data ?? venue} replay={replay.data ?? null} hotspots={[]} marshals={[]} editable={false} resetNonce={0} quality="low"
                       onExitClick={() => {}} onObjectClick={() => {}} onFloorClick={() => {}} onFloorDoubleClick={() => {}} onMove={() => {}} onHotspot={() => {}} />
            {hasAfter && usable(before.data) && (
              <div role="group" aria-label={t("yourplan.before_after")} className="absolute left-1/2 top-3 flex -translate-x-1/2 rounded-[8px] bg-surface p-0.5 shadow-[var(--shadow-float)]">
                {(["before", "after"] as const).map((s) => (
                  <button key={s} type="button" aria-pressed={shownSide === s} onClick={() => setSide(s)}
                          className={cn("min-h-11 rounded-[6px] px-4 text-sm font-medium", shownSide === s ? "bg-signal text-signal-ink" : "text-muted hover:text-ink")}>
                    {t(`yourplan.${s}`)}
                  </button>
                ))}
              </div>
            )}
            <span className="pointer-events-none absolute bottom-3 left-3 rounded-full bg-surface/95 px-3 py-1 text-xs shadow-sm">{sourceTag(shown)}</span>
          </section>

          <div className="space-y-4">
            <section aria-labelledby="changes-h" className="space-y-2 rounded-[10px] border border-border bg-surface p-4">
              <h2 id="changes-h" className="font-semibold">{t("yourplan.changes")}</h2>
              {kept.length === 0 ? <p className="text-sm text-muted">{t("yourplan.no_changes")}</p> : (
                <ul className="space-y-2">
                  {kept.map((f) => {
                    const ops = (f.patch?.ops ?? []) as PatchOpIn[];
                    const build = ops.some((o) => CONSTRUCTION.has(o.op));
                    const label = (id: string) => names.get(id) ?? id;
                    const fixConflicts = lockConflicts(venue, ops);
                    return (
                      <li key={f.fix_id} className="rounded-[8px] border border-border p-2.5 text-sm">
                        <div className="flex items-start justify-between gap-2">
                          <p className="font-medium">{human(f.title)}</p>
                          {build ? <Badge tone="signal"><Hammer />{t("yourplan.construction")}</Badge> : <Badge tone="outline"><Workflow />{t("yourplan.operational")}</Badge>}
                        </div>
                        <p className="mt-1 text-muted">{[...ops.map((o) => describeOp(o as Record<string, unknown>, label)), ...(f.operational ?? []).map((e) => describeEvent(e as Record<string, unknown>, label))].join(" · ")}</p>
                        {fixConflicts.map((c) => <p key={`${c.id}:${c.op}`} className="mt-1 flex gap-1.5 text-danger"><Lock className="mt-0.5 size-3.5 shrink-0" />{t("check.conflict", { name: label(c.id) })}</p>)}
                      </li>
                    );
                  })}
                </ul>
              )}
              {kept.length > 0 && freshness === "current_after" && <p className="flex gap-1.5 text-sm text-egress"><Check className="mt-0.5 size-4 shrink-0" />{t("yourplan.already_accepted")}</p>}
              {kept.length > 0 && freshness === "current_before" && (
                <div className="space-y-1.5 pt-1">
                  <Button variant="primary" className="w-full" size="lg" disabled={!canAccept || apply.isPending} onClick={accept}>
                    {apply.isPending ? <Spinner /> : <Check />}{t("yourplan.accept")}
                  </Button>
                  {conflicts.length > 0 ? <p className="text-sm text-danger">{t("yourplan.accept_conflicts")}</p>
                    : <p className="text-xs text-muted">{t("yourplan.accept_hint")}</p>}
                </div>
              )}
              {kept.length > 0 && freshness === "stale" && <p className="text-sm text-muted">{t("yourplan.accept_stale")}</p>}
            </section>

            <section aria-labelledby="risks-h" className="space-y-2 rounded-[10px] border border-border bg-surface p-4">
              <h2 id="risks-h" className="font-semibold">{t("yourplan.risks")}</h2>
              {risks.length === 0 ? <p className="text-sm text-muted">{t("yourplan.no_risks")}</p> : (
                <ul className="space-y-2">
                  {risks.map((a) => {
                    const node = view.nodes[`atk:${a.attack_id}`];
                    const r = node ? view.runs[node.run_id] : undefined;
                    return (
                      <li key={a.attack_id} className="rounded-[8px] border border-border p-2.5 text-sm">
                        <div className="flex items-start justify-between gap-2">
                          <p className="font-medium">{human(a.title)}</p>
                          {r && (r.is_break ? <Badge tone="danger">{t("work.breaks")}</Badge> : <Badge tone="egress">{t("work.holds")}</Badge>)}
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

            <div className="flex flex-wrap gap-2">
              <Button asChild><Link to={`/p/${p.id}/describe`}><Pencil />{t("yourplan.change_venue")}</Link></Button>
              <Button onClick={testAgain} disabled={start.isPending}><Swords />{t("yourplan.test_again")}</Button>
              <Button asChild variant="link" className="hidden xl:inline-flex"><Link to={`/p/${p.id}/expert`}>{t("journey.expert")}</Link></Button>
            </div>
          </div>
        </div>
      </main>
    </JourneyShell>
  );
}
