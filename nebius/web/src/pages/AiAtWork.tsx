/** Step 2 of the guided journey (route `/p/:projectId/work`): honest progress of the AI test,
 * the latest finished simulation in 3D, and the attacks and fixes as they arrive. */
import { useQueryClient } from "@tanstack/react-query";
import { Check, CircleAlert, CircleDashed, CircleMinus, ExternalLink, Loader2, Square, WifiOff, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { qk, useProject, useRun, useRunVenue, useSession, useSessions, useStopSession } from "@/api/queries";
import { useSessionStream } from "@/api/useSessionStream";
import { Confirm } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";
import { ScriptCode } from "@/journey/ScriptCode";
import { runOutcome } from "@/lib/evidence";
import { JourneyShell } from "@/journey/JourneyShell";
import { workSteps } from "@/journey/workSteps";
import { fmtDuration, fmtInt, fmtMoney } from "@/lib/format";
import { cn } from "@/lib/utils";
import { textHumanizer } from "@/lib/venueText";
import { useReplay } from "@/replay/useReplay";
import { SceneRoot } from "@/scene/SceneRoot";
import { usePlayback } from "@/state/playback";
import { useUi } from "@/state/ui";
import { PeopleLegend } from "@/panels/Overlays";
import { FloorSwitch } from "@/panels/FloorSwitch";

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
  const visible = showAll ? cards : cards.slice(-4);

  return (
    <JourneyShell step="work" projectId={projectId} title={project.data?.name} back={{ to: `/p/${projectId}`, label: t("journey.your_plan") }} wide>
      <Confirm open={confirmStop} onOpenChange={setConfirmStop} title={t("work.stop_title")} body={t("work.stop_body")}
               confirmLabel={t("work.stop")} onConfirm={() => sessionId && stop.mutate(sessionId)} />
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside aria-label={t("work.progress")} className="flex w-full shrink-0 flex-col border-b border-border bg-surface lg:w-[360px] lg:border-b-0 lg:border-r">
          <div className="flex-1 space-y-4 overflow-y-auto p-4">
            <h1 className="text-xl font-semibold tracking-tight">{ended ? (failed ? t("work.failed_title") : t("work.done_title")) : t("work.title")}</h1>
            {failed && <ErrorState message={session.data?.error || t("work.failed_body")} />}
            <div className="space-y-1.5">
              <div className="flex items-baseline justify-between text-sm">
                <span className="font-medium">{ended ? t("work.all_done") : t("work.step_of", { n: Math.min(finishedSteps + 1, steps.length), total: steps.length })}</span>
                <span className="text-muted tabular">{percent}%</span>
              </div>
              <div className="h-3 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label={t("work.progress")}>
                <div className={cn("h-full rounded-full transition-all duration-700", failed ? "bg-danger" : "bg-[linear-gradient(90deg,var(--sky),var(--signal),var(--pink))]")} style={{ width: `${percent}%` }} />
              </div>
              {!ended && <p className="text-sm text-muted">{t("work.leave_ok")}</p>}
            </div>
            <p className="sr-only" aria-live="polite">{current ? t(`work.step_${current.key}`) : ended ? t("work.done_title") : ""}</p>
            <ol className="space-y-1">
              {steps.map((s) => (
                <li key={s.key} className={cn("flex items-start gap-3 rounded-[8px] px-2 py-2", s.status === "running" && "bg-signal-soft/60")}>
                  <span className="mt-0.5 [&_svg]:size-5">
                    {s.status === "done" ? <Check className="text-egress" /> : s.status === "running" ? <Loader2 className="animate-spin text-signal" />
                      : s.status === "failed" ? <CircleAlert className="text-danger" /> : s.status === "skipped" ? <CircleMinus className="text-line" /> : <CircleDashed className="text-line" />}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className={cn("block text-base", s.status === "pending" || s.status === "skipped" ? "text-muted" : "font-medium")}>{t(`work.step_${s.key}`)}</span>
                    {s.status === "running" && view.message && <span className="block text-sm text-muted">{human(view.message)}</span>}
                    {s.status === "skipped" && <span className="block text-sm text-muted">{t("work.skipped")}</span>}
                  </span>
                  {s.elapsedS != null && <span className="text-sm text-muted tabular">{fmtDuration(s.elapsedS)}</span>}
                </li>
              ))}
            </ol>
            {ended && !failed && (
              <div className="space-y-2 rounded-[10px] border border-egress/35 bg-egress-soft p-3">
                <p className="font-semibold">{status === "stopped" ? t("work.stopped_ready") : t("work.ready")}</p>
                <Button asChild variant="primary" size="lg" className="w-full">
                  <Link to={`/p/${projectId}?session=${sessionId}`} autoFocus>{t("work.open_plan")}</Link>
                </Button>
              </div>
            )}
            {!view.connected && !ended && view.lastSeq > 0 && (
              <p className="flex items-center gap-2 text-sm text-muted"><WifiOff className="size-4" />{t("work.reconnecting")}</p>
            )}
          </div>
          <div className="space-y-2 border-t border-border p-4 text-sm text-muted tabular">
            <p>{t("work.sims", { n: fmtInt(okRuns) })}{view.cost ? ` · ${t("work.ai_usage", { tokens: fmtInt(view.cost.tokens_total), cost: fmtMoney(view.cost.cost_usd) })}` : ""}</p>
            {!ended && <Button className="h-11 w-full" disabled={stop.isPending} onClick={() => setConfirmStop(true)}><Square className="size-3.5" />{t("work.stop")}</Button>}
          </div>
        </aside>

        <main id="main" className="flex min-w-0 flex-1 flex-col">
          <div className="relative h-[45vh] lg:h-auto lg:flex-1">
            {venue && <FloorSwitch venue={venue} className="absolute right-3 top-3 z-50" />}
            {venue ? (
              <SceneRoot venue={runVenue.data ?? venue} replay={replay.data ?? null} hotspots={[]} marshals={[]} editable={false}
                         resetNonce={0} quality="low" onExitClick={() => {}} onObjectClick={() => {}} onFloorClick={() => {}}
                         onFloorDoubleClick={() => {}} onMove={() => {}} onHotspot={() => {}} />
            ) : <Skeleton className="m-4 h-[calc(100%-2rem)]" />}
            <PeopleLegend replay={replay.data} className="absolute bottom-3 left-3 z-40 w-52" />
            <span className="pointer-events-none absolute left-3 top-3 rounded-full bg-surface/95 px-3 py-1 text-sm shadow-sm">
              {replay.data ? t("work.showing_latest") : t("work.waiting_sim")}
            </span>
          </div>
          <section aria-label={t("work.trying")} className="border-t border-border bg-surface p-4">
            <div className="mb-2 flex items-baseline justify-between">
              <h2 className="font-semibold">{t("work.trying")}</h2>
              {cards.length > 4 && <Button variant="link" onClick={() => setShowAll((v) => !v)}>{showAll ? t("work.show_less") : t("work.show_all", { n: cards.length })}</Button>}
            </div>
            {cards.length === 0 ? <p className="text-sm text-muted">{ended ? t("work.no_cards") : t("work.cards_soon")}</p> : (
              <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                {visible.map((c) => (
                  <li key={`${c.kind}:${c.id}`} className="animate-deal-in rounded-[10px] border border-border p-3 text-sm">
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-medium leading-snug">{c.title}</p>
                      {c.status === "break" && <Badge tone="danger"><X />{t("work.breaks")}</Badge>}
                      {c.status === "holds" && <Badge tone="egress"><Check />{t("work.holds")}</Badge>}
                      {c.status === "preview" && <Badge tone="neutral">{t("work.preview")}</Badge>}
                      {c.status === "unknown" && <Badge tone="neutral">{t("work.unknown")}</Badge>}
                      {c.status === "kept" && <Badge tone="egress"><Check />{t("work.kept")}</Badge>}
                      {c.status === "not_kept" && <Badge tone="neutral">{t("work.not_kept")}</Badge>}
                      {(c.status === "running" || c.status === "testing") && <Badge tone="signal"><Loader2 className="animate-spin" />{t("work.testing")}</Badge>}
                    </div>
                    <p className="mt-1 text-xs text-muted">{c.kind === "attack" ? t("work.risk") : t("work.fix")}</p>
                    {c.source?.source_url && (
                      <a href={c.source.source_url} target="_blank" rel="noreferrer" className="mt-1 flex min-h-11 items-center gap-1 text-xs text-signal hover:underline">
                        <ExternalLink className="size-3" />{t("work.inspired_by", { what: `${c.source.incident}${c.source.year ? ` (${c.source.year})` : ""}` })}
                      </a>
                    )}
                    <ScriptCode attack={c.attack} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        </main>
      </div>
    </JourneyShell>
  );
}
