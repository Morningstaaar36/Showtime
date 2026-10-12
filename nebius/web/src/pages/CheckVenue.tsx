/** Step 1b of the guided journey (route `/p/:projectId/describe`): the organizer checks and
 * corrects the drafted venue (doors, barriers, people, provenance, locks), then tests it. */
import { AlertTriangle, CircleAlert, DoorOpen, Lock, MousePointer2, Spline, Swords } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { useProject, useScene, useStartSession } from "@/api/queries";
import type { Floor, PatchOpIn, Pt } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Skeleton, Spinner } from "@/components/ui/misc";
import { ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";
import { AskChange, type ProposalPreview } from "@/journey/AskChange";
import { OperationalPlan } from "@/journey/PlanEditor";
import { JourneyShell } from "@/journey/JourneyShell";
import { useVenueEdit } from "@/journey/useVenueEdit";
import { ObjectCard, ObjectLists } from "@/journey/VenueEditor";
import { annotateOp, type ChangeStatus, lockedIds } from "@/lib/annotations";
import { cn, shortId } from "@/lib/utils";
import { displayNames } from "@/lib/venueText";
import { exitRectAt } from "@/scene/geom";
import { SceneRoot } from "@/scene/SceneRoot";
import { usePlayback } from "@/state/playback";
import { useUi } from "@/state/ui";

/** Quick depth (one round): finishes in minutes and keeps AI usage low. */
export const QUICK_TEST = { max_rounds: 1, attacks_per_round: 3, fixes_per_attack: 2, fix_targets: 2 };

const TOOLS = [
  { id: "select", icon: <MousePointer2 />, key: "check.tool_select" },
  { id: "exit", icon: <DoorOpen />, key: "check.tool_door" },
  { id: "barrier", icon: <Spline />, key: "check.tool_barrier" },
] as const;

export function CheckVenuePage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const project = useProject(projectId);
  const p = project.data;
  const scene = useScene(projectId, p?.current_version);
  const start = useStartSession();
  const { submit } = useVenueEdit(projectId);
  const tool = useUi((s) => s.tool);
  const selection = useUi((s) => s.selection);
  const [resetNonce, setResetNonce] = useState(0);
  const [proposal, setProposal] = useState<ProposalPreview | null>(null);
  const [showProposal, setShowProposal] = useState(true);
  const [newChange, setNewChange] = useState<ChangeStatus>("existing");

  useEffect(() => { useUi.getState().resetForProject(); usePlayback.getState().reset(); }, [projectId]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { useUi.getState().setTool("select"); useUi.getState().select(null); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const locked = useMemo(() => (p ? lockedIds(p.version.venue) : new Set<string>()), [p]);
  const names = useMemo(() => (p ? displayNames(p.version.venue) : new Map<string, string>()), [p]);

  if (project.isError) {
    return (
      <JourneyShell step="describe">
        <div className="mx-auto max-w-2xl p-8"><ErrorState message={(project.error as Error).message} onRetry={() => project.refetch()} /></div>
      </JourneyShell>
    );
  }
  if (!p) {
    return <JourneyShell step="describe" projectId={projectId} wide><div className="flex flex-1"><Skeleton className="m-4 flex-1" /></div></JourneyShell>;
  }
  const venue = p.version.venue;
  const errors = p.validation.checks.filter((c) => c.severity === "error");
  const previewing = !!proposal && showProposal;

  const add = (ops: PatchOpIn[], id: string, msg: string) => submit([...ops, annotateOp(id, { change: newChange })], msg, () => useUi.getState().setTool("select"));
  const onFloorClick = (floor: Floor, x: number, y: number) => {
    const tl = useUi.getState().tool;
    if (tl === "exit") {
      const rect = exitRectAt(floor.walkable as Pt[], x, y, 2.0);
      if (!rect) { toast.error(t("check.door_near_wall")); return; }
      const id = shortId("exit");
      add([{ op: "add_exit", floor_id: floor.floor_id, id, width_m: 2.0, polygon: rect, label: newChange === "proposed" ? "Proposed door" : "Door" } as PatchOpIn], id, t("check.msg_door_added"));
    } else if (tl === "barrier") {
      const d = useUi.getState().draft;
      useUi.getState().setDraft([...d, [+x.toFixed(2), +y.toFixed(2)]]);
    } else useUi.getState().select(null);
  };
  const onFloorDoubleClick = (floor: Floor) => {
    const d = useUi.getState().draft;
    if (useUi.getState().tool === "barrier" && d.length >= 2) {
      const id = shortId("barrier");
      add([{ op: "add_barrier_line", floor_id: floor.floor_id, id, points: d.slice(0, 20) } as PatchOpIn], id, t("check.msg_barrier_added"));
      useUi.getState().setDraft([]);
    }
  };
  const test = () => start.mutate({ project_id: p.id, config: QUICK_TEST }, {
    onSuccess: (s) => navigate(`/p/${p.id}/work?session=${s.id}&live=1`),
    onError: (e) => toast.error(e.message, { description: (e as { hint?: string }).hint ?? undefined }),
  });

  return (
    <JourneyShell step="describe" projectId={p.id} title={p.name} back={{ to: "/", label: t("journey.home") }} wide>
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <main id="main" className="relative h-[55vh] min-w-0 lg:h-auto lg:flex-1">
          <SceneRoot venue={previewing ? proposal.venue : venue} replay={null} hotspots={[]} marshals={[]}
                     editable={!previewing} resetNonce={resetNonce} quality="high"
                     highlights={previewing ? proposal.changes : undefined}
                     onExitClick={(e, f) => useUi.getState().select({ kind: "exit", id: e.id, floorId: f.floor_id })}
                     onObjectClick={(kind, id, f) => useUi.getState().select({ kind, id, floorId: f.floor_id })}
                     onFloorClick={onFloorClick} onFloorDoubleClick={onFloorDoubleClick}
                     onMove={(id, dx, dy) => submit([{ op: "move", target: id, dx, dy } as PatchOpIn], t("check.msg_moved", { name: names.get(id) ?? id }))}
                     onHotspot={() => {}} />
          <div className="pointer-events-none absolute inset-0">
            <div role="toolbar" aria-label={t("check.tools")} className="pointer-events-auto absolute left-3 top-3 flex gap-1 rounded-[10px] border border-border bg-surface/95 p-1 shadow-[var(--shadow-float)]">
              {TOOLS.map((x) => (
                <button key={x.id} type="button" aria-pressed={tool === x.id} disabled={previewing}
                        onClick={() => useUi.getState().setTool(x.id)}
                        className={cn("flex min-h-11 items-center gap-1.5 rounded-[6px] px-3 text-sm font-medium transition disabled:opacity-40 [&_svg]:size-[18px]",
                          tool === x.id ? "bg-signal text-signal-ink" : "text-muted hover:bg-surface-2 hover:text-ink")}>
                  {x.icon}<span className="hidden sm:inline">{t(x.key)}</span>
                </button>
              ))}
              <button type="button" onClick={() => setResetNonce((n) => n + 1)} className="min-h-11 rounded-[6px] px-3 text-sm text-muted hover:bg-surface-2 hover:text-ink">{t("check.reset_view")}</button>
            </div>
            {(tool === "exit" || tool === "barrier") && (
              <div className="pointer-events-auto absolute left-3 top-20 max-w-sm space-y-2 rounded-[10px] border border-border bg-surface/95 p-3 text-sm shadow-[var(--shadow-float)]">
                <p>{t(tool === "exit" ? "check.door_hint" : "check.barrier_hint")}</p>
                <fieldset className="flex gap-1">
                  <legend className="sr-only">{t("check.new_is")}</legend>
                  {(["existing", "proposed"] as const).map((c) => (
                    <button key={c} type="button" aria-pressed={newChange === c} onClick={() => setNewChange(c)}
                            className={cn("min-h-11 flex-1 rounded-[6px] border px-2", newChange === c ? "border-signal bg-signal-soft font-medium" : "border-border text-muted")}>
                      {t(c === "existing" ? "check.already_there" : "check.proposed_new")}
                    </button>
                  ))}
                </fieldset>
              </div>
            )}
            {proposal && (
              <div className="pointer-events-auto absolute left-1/2 top-3 flex -translate-x-1/2 rounded-[8px] bg-surface p-0.5 shadow-[var(--shadow-float)]" role="group" aria-label={t("check.preview_toggle")}>
                {[[false, "check.now"], [true, "check.with_change"]].map(([v, k]) => (
                  <button key={String(v)} type="button" aria-pressed={showProposal === v} onClick={() => setShowProposal(v as boolean)}
                          className={cn("min-h-11 rounded-[6px] px-3 text-sm font-medium", showProposal === v ? "bg-signal text-signal-ink" : "text-muted hover:text-ink")}>
                    {t(k as string)}
                  </button>
                ))}
              </div>
            )}
            <div className="absolute inset-x-0 bottom-3 flex justify-center px-3">
              <AskChange project={p} onPreview={(pv) => { setProposal(pv); setShowProposal(true); }} />
            </div>
          </div>
        </main>

        <aside aria-label={t("check.panel")} className="scrollbar-thin flex w-full shrink-0 flex-col border-t border-border bg-surface lg:w-[400px] lg:border-l lg:border-t-0 xl:w-[440px]">
          <div className="flex-1 space-y-5 overflow-y-auto p-4">
            <div>
              <h1 className="text-xl font-semibold tracking-tight">{t("check.title")}</h1>
              <p className="mt-1 text-base text-muted">{t("check.lead")}</p>
              <p className="mt-2 text-xs text-muted tabular">
                {scene.data ? t("check.identity", { v: scene.data.identity.venue_version ?? p.current_version, n: scene.data.objects.length })
                  : scene.isError ? t("check.scene_error") : t("check.identity_loading")}
              </p>
            </div>
            {errors.length > 0 && (
              <ul className="space-y-1.5 rounded-[8px] border border-danger/30 bg-danger-soft p-3 text-sm">
                {errors.map((c, i) => <li key={i} className="flex gap-2"><CircleAlert className="mt-0.5 size-4 shrink-0 text-danger" /><span>{c.message}{c.hint && <span className="block text-muted">{c.hint}</span>}</span></li>)}
              </ul>
            )}
            <OperationalPlan projectId={projectId} />
            {selection && selection.kind !== "hotspot" && selection.kind !== "stair"
              ? <><ObjectCard project={p} scene={scene.data} selection={selection} /><Button variant="link" onClick={() => useUi.getState().select(null)}>{t("check.back_to_list")}</Button></>
              : <ObjectLists project={p} scene={scene.data} />}
          </div>
          <div className="space-y-2 border-t border-border p-4">
            {locked.size > 0 && <p className="flex gap-2 text-sm text-muted"><Lock className="mt-0.5 size-4 shrink-0" />{t("check.locked_count", { n: locked.size })}</p>}
            {errors.length > 0 && <p className="flex gap-2 text-sm text-danger"><AlertTriangle className="mt-0.5 size-4 shrink-0" />{t("check.fix_errors_first")}</p>}
            <Button variant="primary" size="lg" className="w-full" disabled={errors.length > 0 || start.isPending || previewing} onClick={test}>
              {start.isPending ? <Spinner /> : <Swords />}{t("check.test")}
            </Button>
            <p className="text-xs text-muted">{t("check.test_hint")}</p>
          </div>
        </aside>
      </div>
    </JourneyShell>
  );
}
