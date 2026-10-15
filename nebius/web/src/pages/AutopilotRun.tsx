/** "AI at work" for Autopilot (route `/autopilot/:runId`): the eight steps from one sentence (or a
 * project) to a tested plan, the venue as soon as it exists, and the attacks and fixes as they
 * arrive. Moves on to Your plan when the plan is ready; nothing is applied without the organizer. */
import { useQueryClient } from "@tanstack/react-query";
import { Check, CircleAlert, CircleDashed, CircleMinus, ExternalLink, Info, Loader2, Map as MapIcon, RotateCcw, Square, WifiOff, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { qk, useAutopilot, useProject, useRun, useRunVenue, useStartAutopilot, useStopAutopilot } from "@/api/queries";
import { useAutopilotStream } from "@/api/useAutopilotStream";
import { useSessionStream } from "@/api/useSessionStream";
import { Confirm } from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/misc";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";
import { ScriptCode } from "@/journey/ScriptCode";
import { autopilotProgress, autopilotView, isEnded, opensPlan, planHref, retryBody, stepElapsed } from "@/journey/autopilotSteps";
import { JourneyShell } from "@/journey/JourneyShell";
import { runOutcome } from "@/lib/evidence";
import { fmtDuration, fmtInt, fmtMoney } from "@/lib/format";
import { cn } from "@/lib/utils";
import { textHumanizer } from "@/lib/venueText";
import { useReplay } from "@/replay/useReplay";
import { SceneRoot } from "@/scene/SceneRoot";
import { usePlayback } from "@/state/playback";
import { useUi } from "@/state/ui";
import type { AutopilotStep } from "@/types/generated";
import { FloorSwitch } from "@/panels/FloorSwitch";

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

function StepIcon({ status }: { status: AutopilotStep["status"] }) {
  if (status === "done") return <Check className="text-egress" />;
  if (status === "running") return <Loader2 className="animate-spin text-signal motion-reduce:animate-none" />;
  if (status === "failed") return <CircleAlert className="text-danger" />;
  if (status === "skipped") return <CircleMinus className="text-line" />;
  return <CircleDashed className="text-line" />;
}

export function AutopilotRunPage() {
  const { runId = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const run = useAutopilot(runId);
  const stream = useAutopilotStream(runId);
  const view = autopilotView(run.data, stream);
  const final = view.final;
  const ended = isEnded(view.status);
  const failed = view.status === "failed";
  const stop = useStopAutopilot();
  const again = useStartAutopilot();
  const [confirmStop, setConfirmStop] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  // move on by itself only for a run watched while it worked (not one reopened later)
  const sawLive = useRef(false);
  if (!ended && view.status === "running") sawLive.current = true;

  const project = useProject(view.projectId ?? undefined);
  const session = useSessionStream(view.sessionId);
  const venue = project.data?.version.venue;
  const human = useMemo(() => (venue ? textHumanizer(venue) : (s: string) => s), [venue]);

  useEffect(() => { useUi.getState().resetForProject(); usePlayback.getState().reset(); }, [view.projectId]);
  useEffect(() => {
    if (ended) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [ended]);
  const href = planHref(final);
  const autoOpen = !!final && opensPlan(final) && sawLive.current && !reducedMotion();
  // refresh what Your plan reads, then move on when the plan is ready
  useEffect(() => {
    if (!final?.project_id) return;
    void qc.invalidateQueries({ queryKey: qk.sessions(final.project_id) });
    void qc.invalidateQueries({ queryKey: qk.runs(final.project_id) });
    void qc.invalidateQueries({ queryKey: qk.projects });
    if (!autoOpen || !href) return;
    const id = window.setTimeout(() => navigate(href), 2000);
    return () => window.clearTimeout(id);
  }, [final, autoOpen, href, navigate, qc]);

  // the latest finished simulation replays in 3D
  const doneNodes = Object.values(session.nodes).filter((n) => n.status !== "running" && n.status !== "pending");
  const latestRun = doneNodes[doneNodes.length - 1]?.run_id ?? null;
  const sim = useRun(latestRun);
  const finishedRun = sim.data && (sim.data.status === "ok" || sim.data.status === "partial") ? latestRun : null;
  const replay = useReplay(finishedRun, true);
  const runVenue = useRunVenue(finishedRun);
  useEffect(() => {
    if (!replay.data) return;
    usePlayback.getState().setDuration(replay.data.traj.duration);
    usePlayback.getState().setT(0);
    if (!reducedMotion()) usePlayback.getState().play();
  }, [replay.data]);

  const notFound = run.isError && (run.error as { status?: number }).status === 404 && stream.lastSeq === 0;
  if (notFound) {
    return (
      <JourneyShell step="work">
        <main id="main" className="mx-auto w-full max-w-2xl p-6">
          <EmptyState title={t("autopilot.not_found")} body={t("autopilot.not_found_body")}>
            <Button asChild variant="primary" size="lg"><Link to="/">{t("autopilot.go_home")}</Link></Button>
          </EmptyState>
        </main>
      </JourneyShell>
    );
  }

  const progress = autopilotProgress(view.steps, ended);
  const current = progress.current;
  const stopping = !ended && (stop.isPending || stop.isSuccess || stream.logs.some((l) => l.message.startsWith("Stopping")));
  const lastLog = stream.logs.filter((l) => !l.message.startsWith("Stopping")).at(-1);
  const sims = final?.cost?.simulations ?? Object.keys(session.runs).length;
  const title = !ended ? t("autopilot.title") : failed ? t("autopilot.title_failed")
    : view.status === "stopped" ? t("autopilot.title_stopped") : t("autopilot.title_done");
  const tryAgain = () => final && again.mutate(retryBody(final), {
    onSuccess: (r) => navigate(`/autopilot/${r.id}`),
    onError: (e) => toast.error(t("autopilot.start_failed"), { description: e.message }),
  });

  const cards = [
    ...session.attacks.map(({ attack }) => {
      const node = session.nodes[`atk:${attack.attack_id}`];
      const r = node ? session.runs[node.run_id] : undefined;
      return { id: attack.attack_id, kind: "attack" as const, title: human(attack.title), status: r ? runOutcome(r) : node?.status === "running" ? "running" : "waiting", source: attack.inspired_by, attack };
    }),
    ...session.fixes.map(({ fix }) => {
      const node = session.nodes[`fix:${fix.fix_id}`];
      return { id: fix.fix_id, kind: "fix" as const, title: human(fix.title), status: node?.accepted === true ? "kept" : node?.accepted === false ? "not_kept" : "testing", source: null, attack: null };
    }),
  ];
  const visible = showAll ? cards : cards.slice(-4);

  return (
    <JourneyShell step="work" projectId={view.projectId ?? undefined} title={view.projectName ?? undefined} back={{ to: "/", label: t("journey.home") }} wide>
      <Confirm open={confirmStop} onOpenChange={setConfirmStop} title={t("autopilot.stop_title")} body={t("autopilot.stop_body")}
               confirmLabel={t("autopilot.stop")} onConfirm={() => stop.mutate(runId)} />
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside aria-label={t("autopilot.steps")} className="flex w-full shrink-0 flex-col border-b border-border bg-surface lg:w-[380px] lg:border-b-0 lg:border-r">
          <div className="flex-1 space-y-4 overflow-y-auto p-4">
            <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
            {!run.data && stream.lastSeq === 0 ? (
              run.isError ? <ErrorState message={(run.error as Error).message} onRetry={() => run.refetch()} />
                : <div className="space-y-2"><Skeleton className="h-3" /><Skeleton className="h-64" /></div>
            ) : (
              <>
                <div className="space-y-1.5">
                  <div className="flex items-baseline justify-between text-sm">
                    <span className="font-medium">{ended ? t("autopilot.all_done") : t("autopilot.step_of", { n: progress.stepN, total: progress.total })}</span>
                    <span className="text-muted tabular">{progress.percent}%</span>
                  </div>
                  <div className="h-3 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-valuenow={progress.percent} aria-valuemin={0} aria-valuemax={100} aria-label={t("autopilot.progress")}>
                    <div className={cn("h-full rounded-full transition-all duration-700 motion-reduce:transition-none", failed ? "bg-danger" : "bg-[linear-gradient(90deg,var(--sky),var(--signal),var(--pink))]")}
                         style={{ width: `${progress.percent}%` }} />
                  </div>
                  {!ended && <p className="text-sm text-muted">{t("autopilot.leave_ok")}</p>}
                </div>
                <p className="sr-only" aria-live="polite">{current ? t("autopilot.now_doing", { step: t(`autopilot.step_${current.key}`) }) : ended ? title : ""}</p>
                <ol className="space-y-1">
                  {view.steps.map((s) => {
                    const secs = stepElapsed(s, now);
                    const quiet = s.status === "pending" || s.status === "skipped";
                    return (
                      <li key={s.key} aria-current={s.status === "running" ? "step" : undefined}
                          className={cn("flex items-start gap-3 rounded-[8px] px-2 py-2", s.status === "running" && "bg-signal-soft/60", s.status === "failed" && "bg-danger-soft/60")}>
                        <span className="mt-0.5 [&_svg]:size-5" aria-hidden><StepIcon status={s.status} /></span>
                        <span className="min-w-0 flex-1">
                          <span className={cn("block text-base", quiet ? "text-muted" : "font-medium")}>
                            {t(`autopilot.step_${s.key}`)}<span className="sr-only">: {t(`autopilot.status_${s.status}`)}</span>
                          </span>
                          {s.detail && s.status !== "pending" && <span className="block text-sm text-muted">{human(s.detail)}</span>}
                        </span>
                        {secs != null && s.status !== "skipped" && <span className="text-sm text-muted tabular">{fmtDuration(secs)}</span>}
                      </li>
                    );
                  })}
                </ol>
                {!ended && lastLog && (
                  <p className="flex items-start gap-2 text-sm text-muted"><Info className="mt-0.5 size-4 shrink-0" />{human(lastLog.message)}</p>
                )}
                {failed && final && (
                  <div className="space-y-2">
                    <ErrorState message={final.error || t("autopilot.title_failed")} />
                    <div className="flex flex-wrap gap-2">
                      <Button variant="primary" size="lg" onClick={tryAgain} disabled={again.isPending} autoFocus>
                        {again.isPending ? <Loader2 className="animate-spin" /> : <RotateCcw />}{t("autopilot.try_again")}
                      </Button>
                      {final.project_id ? (
                        <Button asChild size="lg"><Link to={`/p/${final.project_id}/describe`}>{t("autopilot.open_what_we_have")}</Link></Button>
                      ) : (
                        <Button asChild size="lg"><Link to="/new/place"><MapIcon />{t("autopilot.draw_instead")}</Link></Button>
                      )}
                    </div>
                  </div>
                )}
                {ended && !failed && final && (
                  <div className="space-y-2 rounded-[10px] border border-egress/35 bg-egress-soft p-3">
                    <p className="font-semibold">
                      {view.status === "finished" ? t("autopilot.ready") : final.session_id ? t("autopilot.stopped_ready") : t("autopilot.stopped_untested")}
                    </p>
                    {final.headline && final.session_id && <p className="text-sm">{human(final.headline)}</p>}
                    {href && final.session_id ? (
                      <Button asChild variant="primary" size="lg" className="w-full">
                        <Link to={href} autoFocus>{t("autopilot.see_plan")}</Link>
                      </Button>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        <Button variant="primary" size="lg" onClick={tryAgain} disabled={again.isPending} autoFocus><RotateCcw />{t("autopilot.try_again")}</Button>
                        {href && <Button asChild size="lg"><Link to={href}>{t("autopilot.open_what_we_have")}</Link></Button>}
                      </div>
                    )}
                    {autoOpen && <p className="text-sm text-muted">{t("autopilot.opening")}</p>}
                  </div>
                )}
                {ended && final && final.notes.length > 0 && (
                  <div className="rounded-[10px] border border-border p-3 text-sm">
                    <p className="font-medium">{t("autopilot.notes")}</p>
                    <ul className="mt-1 list-disc space-y-1 pl-5 text-muted">{final.notes.map((n) => <li key={n}>{human(n)}</li>)}</ul>
                  </div>
                )}
                {!stream.connected && !ended && stream.lastSeq > 0 && (
                  <p className="flex items-center gap-2 text-sm text-muted"><WifiOff className="size-4" />{t("autopilot.reconnecting")}</p>
                )}
              </>
            )}
          </div>
          <div className="space-y-2 border-t border-border p-4 text-sm text-muted tabular">
            <p>
              {view.usd != null && t(ended ? "autopilot.cost_total" : "autopilot.cost", { cost: fmtMoney(view.usd) })}
              {view.usd != null && sims > 0 && " · "}
              {sims > 0 && t("autopilot.sims", { n: fmtInt(sims) })}
            </p>
            {!ended && (
              <Button className="h-11 w-full" disabled={stopping || !view.status} onClick={() => setConfirmStop(true)}>
                {stopping ? <Loader2 className="animate-spin motion-reduce:animate-none" /> : <Square className="size-3.5" />}{stopping ? t("autopilot.stopping") : t("autopilot.stop")}
              </Button>
            )}
          </div>
        </aside>

        <main id="main" className="flex min-w-0 flex-1 flex-col">
          <div className="relative h-[45vh] lg:h-auto lg:flex-1">
            {venue && <FloorSwitch venue={venue} className="absolute left-3 top-3 z-20" />}
            {venue ? (
              <SceneRoot venue={runVenue.data ?? venue} replay={replay.data ?? null} hotspots={[]} marshals={[]} editable={false}
                         resetNonce={0} quality="low" onExitClick={() => {}} onObjectClick={() => {}} onFloorClick={() => {}}
                         onFloorDoubleClick={() => {}} onMove={() => {}} onHotspot={() => {}} />
            ) : view.projectId ? <Skeleton className="m-4 h-[calc(100%-2rem)]" /> : (
              <div className="grid h-full place-items-center bg-hero p-6">
                <p className="flex max-w-xs items-center gap-2 rounded-[var(--radius-panel)] bg-surface/90 px-4 py-3 text-sm text-muted shadow-sm">
                  <MapIcon className="size-4 shrink-0 text-signal" />{t("autopilot.waiting_venue")}
                </p>
              </div>
            )}
            {venue && (
              <span className="pointer-events-none absolute left-3 top-3 rounded-full bg-surface/95 px-3 py-1 text-sm shadow-sm">
                {replay.data ? t("work.showing_latest") : t("work.waiting_sim")}
              </span>
            )}
          </div>
          <section aria-label={t("autopilot.trying")} className="border-t border-border bg-surface p-4">
            <div className="mb-2 flex items-baseline justify-between">
              <h2 className="font-semibold">{t("autopilot.trying")}</h2>
              {cards.length > 4 && <Button variant="link" onClick={() => setShowAll((v) => !v)}>{showAll ? t("work.show_less") : t("work.show_all", { n: cards.length })}</Button>}
            </div>
            {cards.length === 0 ? <p className="text-sm text-muted">{ended ? t("autopilot.no_cards") : t("autopilot.cards_soon")}</p> : (
              <ul className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                {visible.map((c) => (
                  <li key={`${c.kind}:${c.id}`} className="animate-deal-in rounded-[10px] border border-border p-3 text-sm motion-reduce:animate-none">
                    <div className="flex items-start justify-between gap-2">
                      <p className="font-medium leading-snug">{c.title}</p>
                      {c.status === "break" && <Badge tone="danger"><X />{t("work.breaks")}</Badge>}
                      {c.status === "holds" && <Badge tone="egress"><Check />{t("work.holds")}</Badge>}
                      {c.status === "preview" && <Badge tone="neutral">{t("work.preview")}</Badge>}
                      {c.status === "unknown" && <Badge tone="neutral">{t("work.unknown")}</Badge>}
                      {c.status === "kept" && <Badge tone="egress"><Check />{t("work.kept")}</Badge>}
                      {c.status === "not_kept" && <Badge tone="neutral">{t("work.not_kept")}</Badge>}
                      {(c.status === "running" || c.status === "testing") && <Badge tone="signal"><Loader2 className="animate-spin motion-reduce:animate-none" />{t("work.testing")}</Badge>}
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
