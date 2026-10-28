/** Step 1b of the guided journey (route `/p/:projectId/describe`): the organizer checks the
 * drafted venue (doors, people, what is in the way), drags things into place, then tests it. */
import { TestModePicker } from "@/journey/TestModePicker";
import { saveTestMode, savedTestModeId, testMode, testModesOf } from "@/journey/testModes";
import { AlertTriangle, CircleAlert, Hand, MousePointerClick, RotateCcw, SlidersHorizontal, Swords } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { useProject, useScene, useStartSession, useTestModes } from "@/api/queries";
import type { Floor } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Skeleton, Spinner } from "@/components/ui/misc";
import { ErrorState } from "@/components/ui/states";
import { t } from "@/i18n";
import { AskAnything } from "@/journey/AskAnything";
import type { ProposalPreview } from "@/journey/AskChange";
import { type Hit, moveObject, type PaletteItem, placeItem } from "@/journey/dragDrop";
import { useEditorDefaults } from "@/lib/useEditorDefaults";
import { DragBridge, DragGhost } from "@/journey/DragLayer";
import { type Grab, useDrag } from "@/journey/dragStore";
import { DropPalette } from "@/journey/DropPalette";
import { OperationalPlan } from "@/journey/PlanEditor";
import { JourneyShell } from "@/journey/JourneyShell";
import { useVenueEdit } from "@/journey/useVenueEdit";
import { ObjectCard, VenueChecklist } from "@/journey/VenueEditor";
import { FloorsCard } from "@/panels/FloorMenu";
import { EventKindControl } from "@/panels/ZoneProfile";
import { type ChangeStatus, lockedIds } from "@/lib/annotations";
import { cn, shortId } from "@/lib/utils";
import { displayNames } from "@/lib/venueText";
import { useScenePalette } from "@/scene/palette";
import { SceneRoot } from "@/scene/SceneRoot";
import { usePlayback } from "@/state/playback";
import { useUi } from "@/state/ui";
import { FloorSwitch } from "@/panels/FloorSwitch";

export function CheckVenuePage() {
  const { projectId = "" } = useParams();
  const navigate = useNavigate();
  const project = useProject(projectId);
  const p = project.data;
  const scene = useScene(projectId, p?.current_version);
  const start = useStartSession();
  const modes = testModesOf(useTestModes().data);
  // the stored id, resolved against the list on use: the server's list can arrive after this
  const [picked, setPicked] = useState(savedTestModeId);
  const mode = testMode(picked, modes);
  const ed = useEditorDefaults();
  const { submit } = useVenueEdit(projectId);
  const selection = useUi((s) => s.selection);
  const layers = useUi((s) => s.layers);
  const palette = useScenePalette(layers.night);
  const armed = useDrag((s) => s.armed);
  const [resetNonce, setResetNonce] = useState(0);
  const [proposal, setProposal] = useState<ProposalPreview | null>(null);
  const [showProposal, setShowProposal] = useState(true);
  const [newChange, setNewChange] = useState<ChangeStatus>("existing");

  useEffect(() => {
    useUi.getState().resetForProject(); useUi.getState().setTool("select"); usePlayback.getState().reset(); useDrag.getState().reset();
    return () => useDrag.getState().reset();
  }, [projectId]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { useDrag.getState().reset(); useUi.getState().select(null); }
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

  const place = (item: PaletteItem, hit: Hit) => {
    const r = placeItem(venue, hit.floorId, item, hit.x, hit.y, newChange, shortId, ed);
    if ("error" in r) { toast.message(t(r.error)); return; }
    submit(r.ops, t("check.msg_added", { name: r.name }), () => useUi.getState().select({ kind: r.kind, id: r.id, floorId: hit.floorId }));
  };
  const moveTo = (g: Grab, hit: Hit) => {
    const r = moveObject(venue, g.kind, g.id, g.start, [hit.x, hit.y]);
    if (!r) return;
    if ("error" in r) { toast.message(t(r.error)); return; }
    submit(r.ops, t("check.msg_moved", { name: names.get(g.id) ?? g.id }));
  };
  const onFloorClick = (floor: Floor, x: number, y: number) => {
    const item = useDrag.getState().armed;
    if (item) { useDrag.getState().reset(); place(item, { floorId: floor.floor_id, x, y, inside: true }); }
    else useUi.getState().select(null);
  };
  const grab = (kind: Grab["kind"], id: string, floor: Floor, e: { nativeEvent: PointerEvent }) => {
    const d = useDrag.getState();
    if (previewing || d.armed || d.item) return;
    // a crowd area covers much of the floor: it moves only once selected, so the view still turns
    if (kind === "zone" && useUi.getState().selection?.id !== id) return;
    const client: [number, number] = [e.nativeEvent.clientX, e.nativeEvent.clientY];
    const start = d.pick?.(client[0], client[1], floor.floor_id);
    if (!start) return;
    if (d.controls) d.controls.enabled = false; // before the camera sees this press
    d.set({ grab: { kind, id, floorId: floor.floor_id, start: [start.x, start.y], client, active: false, locked: locked.has(id) }, hit: start });
  };
  const test = () => start.mutate({ project_id: p.id, config: mode.config }, {
    onSuccess: (s) => navigate(`/p/${p.id}/work?session=${s.id}&live=1`),
    onError: (e) => toast.error(e.message, { description: (e as { hint?: string }).hint ?? undefined }),
  });

  return (
    <JourneyShell step="describe" projectId={p.id} title={p.name} back={{ to: "/", label: t("journey.home") }} wide fill>
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <main id="main" className="relative h-[55vh] min-w-0 lg:h-auto lg:flex-1">
          <FloorSwitch venue={venue} className="absolute right-3 top-3 z-50" />
          <SceneRoot venue={previewing ? proposal.venue : venue} replay={null} hotspots={[]} marshals={[]}
                     editable={!previewing} resetNonce={resetNonce} quality="high"
                     highlights={previewing ? proposal.changes : undefined}
                     onExitClick={(e, f) => useUi.getState().select({ kind: "exit", id: e.id, floorId: f.floor_id })}
                     onObjectClick={(kind, id, f) => useUi.getState().select({ kind, id, floorId: f.floor_id })}
                     onFloorClick={onFloorClick} onFloorDoubleClick={() => {}}
                     onMove={() => {}} onObjectPointerDown={grab}
                     onHotspot={() => {}}>
            {!previewing && <DragBridge venue={venue} exploded={layers.exploded} />}
            {!previewing && <DragGhost venue={venue} exploded={layers.exploded} palette={palette} />}
          </SceneRoot>
          <div className="pointer-events-none absolute inset-0 z-40">
            <div className="absolute left-3 top-3 flex flex-wrap items-start gap-2">
              <DropPalette disabled={previewing} onPlace={place} onMove={moveTo} />
              <button type="button" onClick={() => setResetNonce((n) => n + 1)} aria-label={t("check.reset_view")} title={t("check.reset_view")}
                      className="pointer-events-auto grid size-[58px] place-items-center rounded-[14px] border border-border bg-surface/95 text-muted shadow-[var(--shadow-float)] hover:text-ink">
                <RotateCcw className="size-5" />
              </button>
            </div>
            {!proposal && (
              <p className={cn("absolute bottom-[4.75rem] left-1/2 flex max-w-[90%] -translate-x-1/2 whitespace-nowrap items-center gap-2 rounded-full px-3.5 py-1.5 text-sm shadow-[var(--shadow-float)]",
                armed ? "bg-signal text-signal-ink" : "bg-surface/95 text-muted")}>
                {armed ? <MousePointerClick className="size-4 shrink-0" /> : <Hand className="size-4 shrink-0" />}
                {t(armed ? "check.armed_hint" : "check.canvas_hint")}
              </p>
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
              <AskAnything project={p} context="check" onPreview={(pv) => { setProposal(pv); setShowProposal(true); }} />
            </div>
          </div>
        </main>

        <aside aria-label={t("check.panel")} className="scrollbar-thin flex w-full shrink-0 flex-col border-t border-border bg-surface lg:w-[400px] lg:border-l lg:border-t-0 xl:w-[440px]">
          <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4">
            <div>
              <h1 className="text-xl font-semibold tracking-tight">{t("check.title")}</h1>
              <p className="mt-1 text-base text-muted">{t("check.lead")}</p>
            </div>
            {errors.length > 0 && (
              <ul className="space-y-1.5 rounded-[10px] border border-danger/30 bg-danger-soft p-3 text-sm">
                {errors.map((c, i) => <li key={i} className="flex gap-2"><CircleAlert className="mt-0.5 size-4 shrink-0 text-danger" /><span>{c.message}{c.hint && <span className="block text-muted">{c.hint}</span>}</span></li>)}
              </ul>
            )}
            {selection && selection.kind !== "hotspot" && selection.kind !== "stair"
              ? <><ObjectCard project={p} scene={scene.data} selection={selection} /><Button variant="link" onClick={() => useUi.getState().select(null)}>{t("check.back_to_list")}</Button></>
              : <><VenueChecklist project={p} scene={scene.data} /><div className="border-t border-border pt-4"><EventKindControl project={p} /></div></>}
            <details className="rounded-[10px] border border-border">
              <summary className="flex min-h-11 cursor-pointer items-center gap-2 px-3 text-sm font-semibold">
                <SlidersHorizontal className="size-4 text-muted" />{t("check.more_options")}
              </summary>
              <div className="space-y-4 border-t border-border p-3">
                <p className="text-sm text-muted">{t("check.more_options_hint")}</p>
                <fieldset className="space-y-1.5">
                  <legend className="mb-1 text-sm">{t("check.new_items_are")}</legend>
                  <div className="flex gap-1">
                    {(["existing", "proposed"] as const).map((c) => (
                      <button key={c} type="button" aria-pressed={newChange === c} onClick={() => setNewChange(c)}
                              className={cn("min-h-11 flex-1 rounded-[8px] border px-2 text-sm", newChange === c ? "border-signal bg-signal-soft font-medium" : "border-border text-muted")}>
                        {t(c === "existing" ? "check.already_there" : "check.proposed_new")}
                      </button>
                    ))}
                  </div>
                </fieldset>
                <OperationalPlan projectId={projectId} />
                {p.version.venue.mode === "indoor" && <div className="border-t border-border pt-4"><FloorsCard project={p} /></div>}
              </div>
            </details>
          </div>
          <div className="space-y-2 border-t border-border p-4">
            {errors.length > 0 && <p className="flex gap-2 text-sm text-danger"><AlertTriangle className="mt-0.5 size-4 shrink-0" />{t("check.fix_errors_first")}</p>}
            <TestModePicker modes={modes.modes} value={mode.id} disabled={start.isPending} onChange={(m) => { setPicked(m); saveTestMode(m); }} />
            <Button variant="primary" size="lg" className="w-full" disabled={errors.length > 0 || start.isPending || previewing} onClick={test}>
              {start.isPending ? <Spinner /> : <Swords />}{t("check.test")}
            </Button>
            <p className="text-xs text-muted">{t("check.test_hint_mode", { m: mode.minutes, what: t(`check.mode_${mode.id}_hint`) })}</p>
          </div>
        </aside>
      </div>
    </JourneyShell>
  );
}
