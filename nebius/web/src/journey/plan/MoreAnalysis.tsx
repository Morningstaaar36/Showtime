/** Expert view › Analysis: the deeper looks at a tested plan that Your plan keeps out of the
 * organizer's way. Scenarios (every tested scenario as a card, the evidence, the failure map, the
 * scenario library and the deeper checks), Sandboxes (the AI-written scenarios, Rewind, the stress
 * test at scale, every run) and, for a tall building, Floors. Watching a run opens it in Simulate. */
import { Building2, ShieldCheck, Swords } from "lucide-react";
import { useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { useRewind, useRun, useSeedCheck, useSensitivity, useSession, useSessions, useSettings, useStress } from "@/api/queries";
import type { ProjectDetail } from "@/api/types";
import { useSessionStream } from "@/api/useSessionStream";
import { EmptyState } from "@/components/ui/states";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { t } from "@/i18n";
import { displayNames, textHumanizer } from "@/lib/venueText";
import { thresholdsOf } from "@/panels/verdict";
import { useReplay } from "@/replay/useReplay";
import { useUi } from "@/state/ui";
import { EvidencePanel } from "./EvidencePanel";
import { FailureMapSlot } from "./FailureMapSlot";
import { FloorsTab } from "./FloorsTab";
import { stressByAttack } from "./gallery";
import { RangePanel } from "./RangePanel";
import { rangeVerdict } from "./range";
import { bestLine } from "./rewind";
import { SandboxesTab } from "./SandboxesTab";
import { DeeperChecks, ScenarioCards, ScenarioCatalogue } from "./ScenarioGallery";
import { scenarioRows } from "./scenarios";
import { SeedPanel } from "./SeedPanel";
import { seedRangeLines } from "./seeds";
import { rowOutcome, stressCounter } from "./stress";

export const ANALYSIS_TABS = ["scenarios", "sandboxes", "floors"] as const;
type AnalysisTab = (typeof ANALYSIS_TABS)[number];

export function MoreAnalysis({ project }: { project: ProjectDetail }) {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const venue = project.version.venue;
  const sessions = useSessions(project.id);
  const sessionId = params.get("session") ?? sessions.data?.[0]?.id ?? null;
  const session = useSession(sessionId);
  const summary = session.data?.summary ?? null;
  const ended = session.data?.status === "finished" || session.data?.status === "stopped";
  const view = useSessionStream(ended ? sessionId : null);
  const rewind = useRewind(sessionId);
  const stress = useStress(project.id);
  const seedCheck = useSeedCheck(sessionId);
  const sensitivity = useSensitivity(sessionId);
  const th = thresholdsOf(useSettings().data?.effective ?? {});
  const multi = venue.floors.length > 1;
  const wanted = params.get("tab");
  const tab: AnalysisTab = (ANALYSIS_TABS as readonly string[]).includes(wanted ?? "") && (wanted !== "floors" || multi) ? wanted as AnalysisTab : "scenarios";
  const go = (next: string) => setParams((prev) => { const q = new URLSearchParams(prev); q.set("tab", next); return q; }, { replace: true });

  const names = useMemo(() => displayNames(venue), [venue]);
  const human = useMemo(() => textHumanizer(venue), [venue]);
  const label = (id: string) => names.get(id) ?? id;
  const rows = useMemo(() => scenarioRows(view.nodes, view.runs, summary?.attacks ?? [], summary?.fixes ?? [], human),
    [view.nodes, view.runs, summary, human]);
  // the floors read the plan with its fixes when there is one, else the plan as tested
  const afterId = summary?.final_run_id ?? summary?.baseline_run_id ?? null;
  const floorRun = useRun(multi && tab === "floors" ? afterId : null);
  const floorReplay = useReplay(floorRun.data && (floorRun.data.status === "ok" || floorRun.data.status === "partial") ? floorRun.data.id : null, tab === "floors");

  // a run is watched in Simulate, Expert view's replay
  const watch = (runId: string) => { useUi.getState().setActiveRun(runId); navigate(`/p/${project.id}/expert/simulate`); };

  if (!sessionId || !session.data) {
    return (
      <div className="mx-auto max-w-2xl p-8">
        <EmptyState icon={<Swords />} title={t("analysis.untested")} body={t("analysis.untested_body")} />
      </div>
    );
  }

  const attacks = summary?.attacks ?? [];
  const worst = attacks.find((a) => a.attack_id === summary?.worst_attack_id);
  const rewindRec = rewind.data ?? null;
  const stressRec = stress.data ?? null;
  const checkStatus = {
    rewind: !rewindRec ? t("plan.not_run") : rewindRec.status === "running" ? t("plan.running") : rewindRec.status === "done" ? bestLine(rewindRec) : t("plan.not_run"),
    stress: !stressRec ? t("plan.not_run") : stressRec.status === "running" ? stressCounter(stressRec).text
      : t("plan.stress_done", { k: stressRec.rows.filter((r) => rowOutcome(r) === "breaks").length, n: stressRec.rows.length }),
    seeds: seedRangeLines(seedCheck.data)?.[0] ?? (seedCheck.data?.status === "running" ? t("plan.running") : t("plan.not_run")),
    range: !sensitivity.data || sensitivity.data.status === "none" ? t("plan.not_run") : rangeVerdict(sensitivity.data).text,
  };
  const m = floorRun.data?.result?.metrics;
  const allOutS = m && m.agents_not_evacuated === 0 && m.evac_time_max_s != null ? m.evac_time_max_s : null;

  return (
    <div className="scrollbar-thin h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl space-y-4 p-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("analysis.title")}</h1>
          <p className="max-w-prose text-muted">{t("analysis.lead")}</p>
        </div>
        <Tabs value={tab} onValueChange={go} className="space-y-4">
          <TabsList aria-label={t("analysis.tabs")}>
            <TabsTrigger value="scenarios" className="flex min-h-11 items-center gap-2 [&_svg]:size-4"><Swords />{t("plan.tab_scenarios")}</TabsTrigger>
            <TabsTrigger value="sandboxes" className="flex min-h-11 items-center gap-2 [&_svg]:size-4"><ShieldCheck />{t("plan.tab_sandboxes")}</TabsTrigger>
            {multi && <TabsTrigger value="floors" className="flex min-h-11 items-center gap-2 [&_svg]:size-4"><Building2 />{t("plan.tab_floors")}</TabsTrigger>}
          </TabsList>

          <TabsContent value="scenarios" className="space-y-6">
            <ScenarioCards rows={rows} attacks={attacks} name={label} stress={stressByAttack(stressRec)} danger={th.danger}
                           onPlay={(row) => watch(row.runId)} />
            <EvidencePanel attacks={attacks} human={human} />
            <FailureMapSlot projectId={project.id} sessionId={sessionId} onSelectRun={(runId) => watch(runId)}
                            hasArchive={!ended || !summary || "archive" in summary} />
            <ScenarioCatalogue projectId={project.id} version={project.current_version} onPlay={(runId) => watch(runId)} danger={th.danger} />
            <DeeperChecks status={checkStatus} panels={{
              seeds: <SeedPanel sessionId={sessionId} human={human} />,
              range: <RangePanel sessionId={sessionId} />,
            }} />
          </TabsContent>

          <TabsContent value="sandboxes">
            <SandboxesTab view={view} attacks={attacks} sessionId={sessionId} projectId={project.id}
                          worstTitle={worst ? human(worst.title) : null} human={human} />
          </TabsContent>

          {multi && (
            <TabsContent value="floors">
              <FloorsTab venue={venue} traj={floorReplay.data?.traj ?? null} allOutS={allOutS}
                         onWatch={(floorId) => { useUi.getState().setFloorView(floorId); if (afterId) watch(afterId); }} />
            </TabsContent>
          )}
        </Tabs>
      </div>
    </div>
  );
}
