import { useQuery } from "@tanstack/react-query";
import { CloudOff, Monitor, SearchX, ServerCrash } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { api } from "@/api/client";
import { useCountdown, useFeatures, useHealth, usePatchProject, useProject, useRedo, useRun, useRuns, useSettings, useStartRun, useTier1, useUndo } from "@/api/queries";
import type { Exit, Floor, Hotspot, PatchOpIn, Pt, RunResult, Venue } from "@/api/types";
import { AppShell } from "@/app/AppHeader";
import { Skeleton } from "@/components/ui/misc";
import { Banner, ErrorState } from "@/components/ui/states";
import { Button } from "@/components/ui/button";
import { t } from "@/i18n";
import { fmtNum } from "@/lib/format";
import { shortId } from "@/lib/utils";
import { AskDialog } from "@/panels/AskDialog";
import { CommandBar } from "@/panels/CommandBar";
import { PlanInspector } from "@/panels/Inspector";
import { DensityLegend, PlanCompass, TierChip } from "@/panels/Overlays";
import { useTour } from "@/panels/Tour";
import { RedTeamPanel, useRedTeamSession } from "@/panels/RedTeamPanel";
import { ReportView } from "@/panels/ReportView";
import { SimulatePanel } from "@/panels/SimulatePanel";
import { Timeline, type TimelineMarker } from "@/panels/Timeline";
import { ToolRail } from "@/panels/ToolRail";
import { TopBar } from "@/panels/TopBar";
import { tierLabel, type Thresholds } from "@/panels/verdict";
import { ViewMenu } from "@/panels/ViewMenu";
import { useReplay } from "@/replay/useReplay";
import { exitRectAt, polygonArea, venueBounds } from "@/scene/geom";
import type { MarshalNote } from "@/scene/ReplayLayers";
import { SceneRoot } from "@/scene/SceneRoot";
import { usePlayback } from "@/state/playback";
import { type Mode, type Tool, useUi } from "@/state/ui";

const MODES: Mode[] = ["plan", "simulate", "redteam", "report"];

/** Expert view needs a desktop-sized screen; below it a notice points back to the simple view. */
const WIDE = "(min-width: 1024px)";
function useWide(): boolean {
  return useSyncExternalStore(
    (cb) => { const mq = window.matchMedia(WIDE); mq.addEventListener("change", cb); return () => mq.removeEventListener("change", cb); },
    () => window.matchMedia(WIDE).matches,
  );
}

export function WorkspacePage() {
  const { projectId = "", mode: rawMode } = useParams();
  const [searchParams] = useSearchParams();
  const mode: Mode = MODES.includes(rawMode as Mode) ? (rawMode as Mode) : "plan";
  const navigate = useNavigate();
  const project = useProject(projectId);
  const runs = useRuns(projectId);
  const health = useHealth();
  const features = useFeatures();
  const settings = useSettings();
  const ui = useUi();
  const [resetNonce, setResetNonce] = useState(0);
  const [ask, setAsk] = useState<{ open: boolean; hotspot: Hotspot | null }>({ open: false, hotspot: null });
  const patch = usePatchProject(projectId);
  const undo = useUndo(projectId);
  const redo = useRedo(projectId);
  const start = useStartRun();
  const tier1 = useTier1(projectId);

  useEffect(() => { useUi.getState().resetForProject(); usePlayback.getState().reset(); }, [projectId]);
  useEffect(() => { useUi.getState().setTool("select"); useUi.getState().select(null); }, [mode]);

  const p = project.data;
  const version = p?.current_version;
  const venue = p?.version.venue;
  const eff = settings.data?.effective ?? {};
  const th: Thresholds = { warn: Number(eff.density_warn_ppm2 ?? 3.5), danger: Number(eff.density_danger_ppm2 ?? 5), dangerMinS: 5 };

  // Instant estimate of the current plan (Tier 1, milliseconds).
  const estimate = useQuery({
    queryKey: ["tier1", projectId, version],
    enabled: !!p && p.validation.ok,
    queryFn: () => api.post<RunResult>(`/venues/${projectId}/tier1`, {}),
  });

  // Which run is shown: the one picked, else the latest finished stress test of this version.
  const autoRun = useMemo(() => {
    // plain runs of this version (stress tests, or a red-team baseline): no attack, no fix
    const list = (runs.data ?? []).filter((r) => r.venue_version === version && !r.attack_id && !r.fix_id);
    return list.find((r) => r.tier === 3 && (r.status === "ok" || r.status === "partial"))?.id
      ?? list.find((r) => r.status === "running" || r.status === "queued")?.id ?? null;
  }, [runs.data, version]);
  const runId = ui.activeRunId ?? autoRun;
  const run = useRun(runId);
  const finished = run.data && (run.data.status === "ok" || run.data.status === "partial");
  const replay = useReplay(finished ? runId : null, mode !== "plan" && mode !== "report");
  // "Stress test finished" when a run the user is watching completes (not for runs opened later)
  const watched = useRef<{ id: string | null; status: string | undefined }>({ id: null, status: undefined });
  useEffect(() => {
    const st = run.data?.status;
    const prev = watched.current;
    if (run.data && prev.id === run.data.id && (prev.status === "queued" || prev.status === "running")) {
      const label = run.data.label || "Simulation";
      if (st === "ok" || st === "partial") {
        toast.success(label === "Stress test" ? t("workspace.stress_test_finished") : `${label} finished`);
      } else if (st === "failed" || st === "timeout") {
        toast.error(label === "Stress test" ? t("workspace.stress_test_failed") : `${label} didn't finish`,
                    { description: run.data.error ?? undefined });
      }
    }
    watched.current = { id: run.data?.id ?? null, status: st };
    if (st === "ok" || st === "partial") void runs.refetch();
  }, [run.data?.id, run.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (replay.data) {
      usePlayback.getState().setDuration(replay.data.traj.duration);
      usePlayback.getState().setT(0);
      usePlayback.getState().play();
    }
  }, [replay.data]);

  const countdown = useCountdown(projectId, { run_id: finished ? runId : null }, version);
  const redteam = useRedTeamSession(projectId);
  const compareId = mode !== "plan" ? ui.compareRunId : null;
  const compareReplay = useReplay(compareId, !!compareId);
  const compareVenue = useQuery({
    queryKey: ["run-venue", compareId],
    enabled: !!compareId,
    staleTime: Infinity,
    retry: false,
    queryFn: () => api.get<Venue>(`/runs/${compareId}/venue`),
  });
  const runVenue = useQuery({
    queryKey: ["run-venue", runId],
    enabled: !!runId && !!finished && mode !== "plan",
    staleTime: Infinity,
    retry: false,
    queryFn: () => api.get<Venue>(`/runs/${runId}/venue`),
  });

  // "Break it yourself": instant estimate with blocked exits.
  useEffect(() => {
    if (!p) return;
    if (!ui.blockedExits.length) { useUi.getState().setTier1Preview(null); return; }
    tier1.mutate({ blocked_exits: ui.blockedExits }, {
      onSuccess: (r) => useUi.getState().setTier1Preview(r),
      onError: (e) => toast.error(e.message),
    });
  }, [ui.blockedExits.join(","), version]); // eslint-disable-line react-hooks/exhaustive-deps

  const submitOps = useCallback((ops: PatchOpIn[], message?: string) => {
    patch.mutate({ patch: { ops }, message }, {
      onSuccess: (r) => toast.success(t("workspace.saved", { n: r.version.version }), {
        action: { label: t("common.undo"), onClick: () => undo.mutate() },
      }),
      onError: (e) => toast.error(e.message, { description: (e as { hint?: string }).hint }),
    });
  }, [patch, undo]);

  const runStress = useCallback(() => {
    if (!p) return;
    start.mutate({ project_id: p.id, tier: 3, label: "Stress test" }, {
      onSuccess: (r) => {
        useUi.getState().setActiveRun(r.id);
        if (mode === "plan") navigate(`/p/${p.id}/expert/simulate`);
        if (r.status === "ok" || r.status === "partial") {
          // same plan and seed as an earlier run: runs are content-addressed, so the result is reused
          toast.success(t("workspace.stress_test_finished"), { description: "This exact plan was simulated before; showing that result." });
        }
      },
      onError: (e) => toast.error(e.message, { description: (e as { hint?: string }).hint }),
    });
  }, [p, start, mode, navigate]);

  // Keyboard shortcuts.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement)?.isContentEditable) return;
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) { if (p?.can_redo) redo.mutate(); } else if (p?.can_undo) undo.mutate();
        return;
      }
      if (mod) return;
      const tools: Record<string, Tool> = { v: "select", e: "exit", b: "barrier", z: "zone", m: "measure", x: "block" };
      const k = e.key.toLowerCase();
      if (k === "escape") { useUi.getState().setTool("select"); useUi.getState().select(null); }
      else if (k === "r") runStress();
      else if (["1", "2", "3", "4"].includes(k)) navigate(`/p/${projectId}/expert/${MODES[Number(k) - 1]}`);
      else if (tools[k] && (mode === "plan" || ["select", "block", "measure"].includes(tools[k]))) useUi.getState().setTool(tools[k]);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [p, mode, projectId, runStress, navigate, undo, redo]);

  const result = run.data?.result ?? null;
  // the verdict in Plan prefers a confirmed simulation of exactly this version over the formula
  const confirmed = finished && run.data && run.data.tier === 3 && run.data.venue_version === version
    && !run.data.attack_id && !run.data.fix_id ? result : null;
  const shownRun = mode === "simulate" ? (ui.tier1Preview ?? (finished ? result : estimate.data))
    : mode === "redteam" && finished ? result : confirmed ?? estimate.data;
  const tour = useTour({ projectId, version: version ?? 0, venue, run: shownRun, autoStart: searchParams.get("tour") === "1" });
  const wide = useWide();

  if (project.isError) {
    const missing = (project.error as { status?: number }).status === 404;
    return (
      <AppShell className="bg-hero">
        <div className="mx-auto w-full max-w-2xl space-y-4 px-4 py-12">
          <ErrorState title={missing ? t("workspace.missing_title") : undefined}
                      message={missing ? t("workspace.missing_body") : (project.error as Error).message}
                      hint={missing ? null : (project.error as { hint?: string }).hint}
                      onRetry={missing ? undefined : () => project.refetch()} />
          <Button asChild variant="primary" size="lg"><Link to="/projects">{t("workspace.missing_back")}</Link></Button>
        </div>
      </AppShell>
    );
  }
  if (!wide) {
    return (
      <AppShell className="bg-hero">
        <div className="mx-auto flex w-full max-w-md flex-col items-center px-4 py-16 text-center">
          <span className="grid size-16 place-items-center rounded-full bg-signal-soft text-signal [&_svg]:size-8" aria-hidden><Monitor /></span>
          <h1 className="mt-5 text-2xl font-bold leading-tight tracking-tight">{t("workspace.small_title")}</h1>
          <p className="mt-2 text-lg text-muted">{t("workspace.small_body")}</p>
          <Button asChild variant="primary" size="lg" className="mt-6"><Link to={`/p/${projectId}`}>{t("workspace.small_back")}</Link></Button>
        </div>
      </AppShell>
    );
  }
  if (!p || !venue) {
    return (
      <div className="flex h-full flex-col">
        <div className="h-12 border-b border-border bg-surface" />
        <div className="flex flex-1"><Skeleton className="m-4 flex-1" /><div className="w-[380px] space-y-3 border-l border-border p-4"><Skeleton className="h-28" /><Skeleton className="h-40" /></div></div>
      </div>
    );
  }

  const sessionRows = redteam.sessions.data ?? [];
  const aiCost = sessionRows.length
    ? { tokens: sessionRows.reduce((a, r) => a + r.tokens, 0), usd: sessionRows.reduce((a, r) => a + r.cost_usd, 0) }
    : null;
  const [bx0, by0, bx1, by1] = venueBounds(venue);
  const span = Math.max(bx1 - bx0, by1 - by0);
  const shownHotspots: Hotspot[] = mode === "simulate"
    ? (ui.tier1Preview?.hotspots ?? (finished ? result?.hotspots ?? [] : []))
    : mode === "redteam" && finished ? result?.hotspots ?? [] : [];
  // marshal bubbles belong to a replay, not to the plan being edited
  const marshals = mode === "plan" || !finished ? []
    : ((result?.extensions as Record<string, unknown> | undefined)?.marshals as MarshalNote[] | undefined) ?? [];
  const markers: TimelineMarker[] = [
    ...(((result?.extensions as Record<string, unknown> | undefined)?.event_log as { t_s: number; type: string }[] | undefined) ?? [])
      .filter((e) => ["block_exit", "surge", "counterflow", "marshal_redirect", "intervention", "slowdown"].includes(e.type))
      .map((e) => ({ t: e.t_s, label: e.type.replace("_", " "), tone: (e.type === "block_exit" ? "danger" : e.type === "marshal_redirect" || e.type === "intervention" ? "egress" : "caution") as TimelineMarker["tone"] })),
    ...(result?.hotspots ?? []).slice(0, 3).map((h) => ({ t: h.t_s, label: `${fmtNum(h.peak_density_ppm2, 1)} people per m²`, tone: (h.level === "danger" ? "danger" : "caution") as TimelineMarker["tone"] })),
  ];

  const onExitClick = (exit: Exit, floor: Floor) => {
    if (mode === "simulate" && (ui.tool === "block" || ui.tool === "select")) {
      if (ui.tool === "block") { ui.toggleBlocked(exit.id); return; }
    }
    ui.select({ kind: "exit", id: exit.id, floorId: floor.floor_id });
  };
  const onFloorClick = (floor: Floor, x: number, y: number) => {
    const tool = useUi.getState().tool;
    if (mode !== "plan" && tool !== "measure") { ui.select(null); return; }
    if (tool === "exit") {
      const rect = exitRectAt(floor.walkable as Pt[], x, y, 2.0);
      if (!rect) { toast.error("Click closer to an outer wall to place an exit."); return; }
      submitOps([{ op: "add_exit", floor_id: floor.floor_id, id: shortId("exit"), width_m: 2.0, polygon: rect, label: "New exit" } as PatchOpIn], "Added exit");
      ui.setTool("select");
    } else if (tool === "barrier" || tool === "zone" || tool === "measure") {
      const d = useUi.getState().draft;
      if (tool === "measure" && d.length >= 2) ui.setDraft([[x, y]]);
      else ui.setDraft([...d, [+x.toFixed(2), +y.toFixed(2)]]);
    } else ui.select(null);
  };
  const onFloorDoubleClick = (floor: Floor) => {
    const tool = useUi.getState().tool;
    const d = useUi.getState().draft;
    if (tool === "barrier" && d.length >= 2) {
      submitOps([{ op: "add_barrier_line", floor_id: floor.floor_id, id: shortId("barrier"), points: d.slice(0, 20) } as PatchOpIn], "Added barrier");
      ui.setDraft([]);
    } else if (tool === "zone" && d.length >= 3) {
      const people = Math.round(polygonArea(d) * 1.5);
      submitOps([{ op: "add_zone", floor_id: floor.floor_id, id: shortId("zone"), polygon: d, people, label: "New zone" } as PatchOpIn], "Added zone");
      ui.setDraft([]);
    }
  };

  const h = health.data?.providers;
  const banners = [
    h && !h.llm.ok && { key: "llm", tone: "caution" as const, icon: <CloudOff />, text: t("workspace.llm_down") },
    h && !h.sandbox.ok && { key: "sb", tone: "danger" as const, icon: <ServerCrash />, text: t("workspace.sandbox_down") },
    mode === "redteam" && features.data && !features.data.search_live && { key: "s", tone: "signal" as const, icon: <SearchX />, text: t("workspace.search_off") },
  ].filter(Boolean) as { key: string; tone: "caution" | "danger" | "signal"; icon: React.ReactNode; text: string }[];

  const tone = shownRun?.tier === 3 ? "confirmed" : shownRun?.tier === 2 ? "partial" : "estimate";

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <AskDialog open={ask.open} onOpenChange={(v) => setAsk((a) => ({ ...a, open: v }))} projectId={p.id}
                 runId={finished ? runId : null} hotspot={ask.hotspot} />
      <TopBar project={p} mode={mode} countdown={countdown.data} cost={aiCost} />
      {tour.overlay}
      {banners.map((b) => <Banner key={b.key} tone={b.tone} icon={b.icon}>{b.text}</Banner>)}
      {mode === "report" ? (
        <main id="main" className="min-h-0 flex-1"><ReportView project={p} /></main>
      ) : (
        <div className="relative flex min-h-0 flex-1">
          <main id="main" className="relative min-w-0 flex-1">
            {compareId && compareReplay.data && (
              <div className="absolute inset-y-0 left-0 z-0 w-1/2 border-r-2 border-ink/70">
                <SceneRoot venue={compareVenue.data ?? venue} replay={compareReplay.data} hotspots={[]} marshals={[]}
                           editable={false} resetNonce={resetNonce} quality="low" clock={false}
                           onExitClick={() => {}} onObjectClick={() => {}} onFloorClick={() => {}}
                           onFloorDoubleClick={() => {}} onMove={() => {}} onHotspot={() => {}} />
                <span className="pointer-events-none absolute bottom-24 left-1/2 -translate-x-1/2 rounded-full bg-danger px-3 py-1 text-xs font-semibold text-white shadow dark:text-plan">Before fixes</span>
              </div>
            )}
            <div className={compareId && compareReplay.data ? "absolute inset-y-0 right-0 w-1/2" : "absolute inset-0"}>
            {compareId && compareReplay.data && (
              <span className="pointer-events-none absolute bottom-24 left-1/2 z-10 -translate-x-1/2 rounded-full bg-egress px-3 py-1 text-xs font-semibold text-white shadow dark:text-plan">After fixes</span>
            )}
            <SceneRoot
              venue={mode !== "plan" && runVenue.data ? runVenue.data : venue}
              replay={mode === "plan" ? null : replay.data ?? null}
              hotspots={shownHotspots}
              marshals={marshals}
              editable={mode === "plan"}
              resetNonce={resetNonce}
              quality="high"
              onExitClick={onExitClick}
              onObjectClick={(kind, id, floor) => ui.select({ kind, id, floorId: floor.floor_id })}
              onFloorClick={onFloorClick}
              onFloorDoubleClick={onFloorDoubleClick}
              onMove={(id, dx, dy) => submitOps([{ op: "move", target: id, dx, dy } as PatchOpIn])}
              onHotspot={(hs) => {
                ui.flyToPoint(hs.x, hs.y, hs.floor_id);
                ui.select({ kind: "hotspot", id: `${hs.floor_id}:${hs.x}:${hs.y}`, floorId: hs.floor_id, x: hs.x, y: hs.y });
                if (finished && !ui.tier1Preview) setAsk({ open: true, hotspot: hs });
              }}
            />
            </div>
            <div className="pointer-events-none absolute inset-0">
              <div className="absolute left-3 top-3"><ToolRail mode={mode} onResetView={() => setResetNonce((n) => n + 1)} /></div>
              {!compareId && (
                <div className="absolute right-3 top-3"><ViewMenu multiFloor={venue.floors.length > 1} tour={tour} /></div>
              )}
              {shownRun && !compareId && (
                <div className="absolute left-1/2 top-3 -translate-x-1/2"><TierChip label={tierLabel(shownRun)} tone={tone} /></div>
              )}
              {compareId && (
                <button type="button" onClick={() => ui.setCompareRun(null)}
                        className="pointer-events-auto absolute left-1/2 top-3 -translate-x-1/2 rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium shadow hover:bg-surface-2">
                  Exit comparison
                </button>
              )}
              {mode === "plan" && ui.tool !== "select" && (
                <div className="absolute left-16 top-3 max-w-sm rounded-[var(--radius-control)] border border-border bg-surface/95 px-3 py-2 text-sm shadow-sm">
                  {t(`tools.${ui.tool === "exit" ? "exit_hint" : ui.tool === "barrier" ? "barrier_hint" : ui.tool === "zone" ? "zone_hint" : "measure"}`)}
                </div>
              )}
              <div className="absolute bottom-3 left-3 flex flex-col items-start gap-2">
                {mode !== "plan" && replay.data?.density && <DensityLegend warn={th.warn} danger={th.danger} />}
                <PlanCompass span={span} />
              </div>
              <div className="absolute inset-x-0 bottom-3 flex justify-center px-40">
                {mode === "plan" && <CommandBar projectId={p.id} onUndo={() => undo.mutate()} />}
                {mode !== "plan" && replay.data && <div className="w-full max-w-3xl"><Timeline markers={markers} /></div>}
              </div>
            </div>
          </main>
          <aside aria-label="Inspector" className={`scrollbar-thin shrink-0 overflow-y-auto border-l border-border bg-surface p-4 ${mode === "redteam" ? "w-[440px] xl:w-[500px]" : "w-[380px] xl:w-[420px]"}`}>
            {mode === "plan" && <PlanInspector project={p} estimate={confirmed ?? estimate.data} th={th} countdown={countdown.data} />}
            {mode === "simulate" && <SimulatePanel project={p} run={run.data} estimate={estimate.data} replay={replay.data ?? null} th={th} onAsk={(h) => setAsk({ open: true, hotspot: h })} />}
            {mode === "redteam" && <RedTeamPanel project={p} sessionId={redteam.sessionId} onPickSession={(id) => redteam.setPicked(id)} />}
          </aside>
        </div>
      )}
    </div>
  );
}
