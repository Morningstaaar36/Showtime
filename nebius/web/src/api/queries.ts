/** TanStack Query hooks for every server resource. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, configureTimeouts } from "./client";
import type { PlanSnapshot } from "@/types/generated";
import type { OpenCaseOut, RealCase } from "@/journey/realCases";
import type {
  SandboxIsolation,
  AskOut,
  Attack,
  CountdownOut,
  EditOut,
  EditResult,
  Features,
  Fix,
  GlossaryItem,
  PatchInput,
  PatchPreview,
  Health,
  ProjectDetail,
  ProjectSummary,
  RunOut,
  RunResult,
  SceneSnapshot,
  SessionOut,
  SettingsOut,
  SimulatorValidation,
  StageCheckResult,
  Template,
  Venue,
  VenueDraft,
  VersionOut,
  WeatherOut,
} from "./types";

export const qk = {
  health: ["health"] as const,
  features: ["features"] as const,
  settings: ["settings"] as const,
  templates: ["templates"] as const,
  projects: ["projects"] as const,
  project: (id: string) => ["project", id] as const,
  versions: (id: string) => ["versions", id] as const,
  runs: (id: string) => ["runs", id] as const,
  run: (id: string) => ["run", id] as const,
  sessions: (id: string) => ["sessions", id] as const,
  session: (id: string) => ["session", id] as const,
  glossary: ["glossary"] as const,
  validation: ["validation"] as const,
  scene: (id: string, version: number | undefined) => ["scene", id, version ?? "current"] as const,
};

export const useHealth = () =>
  useQuery({
    queryKey: qk.health,
    queryFn: async () => {
      const h = await api.get<Health>("/health");
      configureTimeouts(h.client); // the server decides how long the app waits
      return h;
    },
    refetchInterval: 15000,
    retry: 1,
  });
/** One attack from `make sandbox-proof`, as the sandbox reported it. */
export interface SandboxProofRow { kind: "scenario" | "code"; name: string; label: string; static: string | null; inside: string | null; status: string; runtime_s: number; injected?: boolean }
export interface SandboxProof { recorded_at: string; docker: string; image: string; command: string; rows: SandboxProofRow[] }
export const useSandboxProof = () =>
  useQuery({ queryKey: ["sandbox-proof"], queryFn: () => api.get<SandboxProof>("/sandbox/proof"), staleTime: 300_000, retry: false });
export const useFeatures = () =>
  useQuery({ queryKey: qk.features, queryFn: () => api.get<Features>("/features"), staleTime: 60000 });
export const useSettings = () =>
  useQuery({ queryKey: qk.settings, queryFn: () => api.get<SettingsOut>("/settings") });
export const useTemplates = () =>
  useQuery({ queryKey: qk.templates, queryFn: () => api.get<Template[]>("/templates"),
             staleTime: Infinity });
export const useProjects = () =>
  useQuery({ queryKey: qk.projects, queryFn: () => api.get<ProjectSummary[]>("/projects") });
export const useProject = (id: string | undefined) =>
  useQuery({ queryKey: qk.project(id ?? ""), queryFn: () => api.get<ProjectDetail>(`/projects/${id}`),
             enabled: !!id });
export const usePlan = (id: string) =>
  useQuery({ queryKey: ["plan", id], enabled: !!id, queryFn: () => api.get<PlanSnapshot>(`/projects/${id}/plan`) });
export const useVersions = (id: string | undefined) =>
  useQuery({ queryKey: qk.versions(id ?? ""),
             queryFn: () => api.get<VersionOut[]>(`/projects/${id}/versions`), enabled: !!id });
export const useRuns = (id: string | undefined) =>
  useQuery({ queryKey: qk.runs(id ?? ""), queryFn: () => api.get<RunOut[]>(`/projects/${id}/runs`),
             enabled: !!id });
/** The canonical scene snapshot (identity, units, provenance) of one saved version. */
export const useScene = (id: string | undefined, version: number | undefined) =>
  useQuery({ queryKey: qk.scene(id ?? "", version), enabled: !!id && version != null, staleTime: Infinity,
             queryFn: () => api.get<SceneSnapshot>(`/projects/${id}/scene?version=${version}`) });
/** The venue a run simulated (immutable). */
export const useRunVenue = (runId: string | null | undefined) =>
  useQuery({ queryKey: ["run-venue", runId], enabled: !!runId, staleTime: Infinity, retry: false,
             queryFn: () => api.get<Venue>(`/runs/${runId}/venue`) });
export const useGlossary = () =>
  useQuery({ queryKey: qk.glossary, queryFn: () => api.get<GlossaryItem[]>("/glossary"),
             staleTime: Infinity });

/** Simulator vs a real bottleneck experiment (shipped JSON; 404 until `make validate`). */
export const useValidation = () =>
  useQuery({ queryKey: qk.validation, queryFn: () => api.get<SimulatorValidation>("/validation"),
             staleTime: Infinity, retry: false });

/** A run, polled every second while it is queued or running. */
export const useRun = (id: string | null | undefined) =>
  useQuery({
    queryKey: qk.run(id ?? ""),
    queryFn: () => api.get<RunOut>(`/runs/${id}`),
    enabled: !!id,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "queued" || s === "running" ? 1000 : false;
    },
  });

export const useSessions = (projectId: string | undefined) =>
  useQuery({ queryKey: qk.sessions(projectId ?? ""),
             queryFn: () => api.get<SessionOut[]>(`/projects/${projectId}/sessions`),
             enabled: !!projectId, retry: false });

export const useSession = (id: string | null | undefined) =>
  useQuery({
    queryKey: qk.session(id ?? ""),
    queryFn: () => api.get<SessionOut>(`/sessions/${id}`),
    enabled: !!id,
    refetchInterval: (q) => (q.state.data?.status === "running" || q.state.data?.status === "queued" ? 3000 : false),
  });

export const useWeather = (projectId: string | undefined, enabled: boolean) =>
  useQuery({ queryKey: ["weather", projectId], enabled: !!projectId && enabled, retry: false,
             staleTime: 10 * 60_000,
             queryFn: () => api.get<WeatherOut>(`/weather?project_id=${projectId}`) });

export const useStageCheck = (projectId: string | undefined, key: string, enabled: boolean) =>
  useQuery({ queryKey: ["stage", projectId, key], enabled: !!projectId && enabled, staleTime: Infinity,
             queryFn: () => api.post<StageCheckResult>("/stage-check", { project_id: projectId }) });

export interface CountdownInput {
  run_id?: string | null;
  attack?: Attack | null;
  gust_ms?: number | null;
  hazard_time_s?: number | null;
}

export const useCountdown = (projectId: string | undefined, input: CountdownInput, version: number | undefined) =>
  useQuery({
    queryKey: ["countdown", projectId, version, input.run_id ?? null, input.attack?.attack_id ?? null,
               input.gust_ms ?? null, input.hazard_time_s ?? null],
    enabled: !!projectId,
    retry: false,
    queryFn: () => api.post<CountdownOut>(`/projects/${projectId}/countdown`, input),
  });

// --- mutations --------------------------------------------------------------------------

function useInvalidateProject() {
  const qc = useQueryClient();
  return (id: string) => {
    void qc.invalidateQueries({ queryKey: ["plan", id] });
    void qc.invalidateQueries({ queryKey: qk.project(id) });
    void qc.invalidateQueries({ queryKey: qk.versions(id) });
    void qc.invalidateQueries({ queryKey: qk.projects });
    void qc.invalidateQueries({ queryKey: ["countdown", id] });
  };
}

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; template_id?: string; venue?: Venue; description?: string }) =>
      api.post<ProjectSummary>("/projects", body),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.projects }),
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del<void>(`/projects/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.projects }),
  });
}

export function useDuplicateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<ProjectSummary>(`/projects/${id}/duplicate`),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.projects }),
  });
}

export function useRenameProject() {
  const inv = useInvalidateProject();
  return useMutation({
    mutationFn: (v: { id: string; name: string }) => api.patch<ProjectSummary>(`/projects/${v.id}`, { name: v.name }),
    onSuccess: (_d, v) => inv(v.id),
  });
}

export function useImportProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => api.upload<ProjectSummary>("/projects/import", file),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.projects }),
  });
}

export function usePatchProject(id: string) {
  const qc = useQueryClient();
  const inv = useInvalidateProject();
  return useMutation({
    mutationFn: (v: { patch: PatchInput; message?: string; allow_new_errors?: boolean; expected_version?: number }) =>
      api.post<EditResult>(`/projects/${id}/patch`, v),
    onSuccess: (data) => {
      qc.setQueryData<ProjectDetail>(qk.project(id), (old) =>
        old ? { ...old, ...data.project, version: data.version, validation: data.validation } : old);
      inv(id);
    },
  });
}

/** Dry run of a patch: shows a proposal before the organizer accepts it. */
export function usePreviewPatch(id: string) {
  return useMutation({
    mutationFn: (v: { patch: PatchInput; allow_new_errors?: boolean }) =>
      api.post<PatchPreview>(`/projects/${id}/patch/preview`, v),
  });
}

function useHistoryAction(id: string, action: "undo" | "redo") {
  const qc = useQueryClient();
  const inv = useInvalidateProject();
  return useMutation({
    mutationFn: () => api.post<EditResult>(`/projects/${id}/${action}`),
    onSuccess: (data) => {
      qc.setQueryData<ProjectDetail>(qk.project(id), (old) =>
        old ? { ...old, ...data.project, version: data.version, validation: data.validation } : old);
      inv(id);
    },
  });
}
export const useUndo = (id: string) => useHistoryAction(id, "undo");
export const useRedo = (id: string) => useHistoryAction(id, "redo");

export function useRestoreVersion(id: string) {
  const inv = useInvalidateProject();
  return useMutation({
    mutationFn: (version: number) => api.post<EditResult>(`/projects/${id}/restore/${version}`),
    onSuccess: () => inv(id),
  });
}

export function useTextEdit(id: string) {
  const inv = useInvalidateProject();
  return useMutation({
    mutationFn: (v: { text: string; apply: boolean }) => api.post<EditOut>(`/projects/${id}/edit`, v),
    onSuccess: (data) => {
      if (data.status === "applied") inv(id);
    },
  });
}

export interface RunInput {
  project_id: string;
  tier: 2 | 3;
  seed?: number;
  attack?: Attack | null;
  fix?: Fix | null;
  blocked_exits?: string[];
  intervention_at_s?: number | null;
  parent_run_id?: string | null;
  label?: string;
  events?: { type: string; at_s: number; [k: string]: unknown }[];
}

export function useStartRun() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: RunInput) => api.post<RunOut>("/runs", v),
    onSuccess: (data) => {
      qc.setQueryData(qk.run(data.id), data);
      if (data.project_id) void qc.invalidateQueries({ queryKey: qk.runs(data.project_id) });
    },
  });
}

export function useCancelRun() {
  return useMutation({ mutationFn: (id: string) => api.post<{ cancelled: boolean }>(`/runs/${id}/cancel`) });
}

export function useTier1(id: string) {
  return useMutation({
    mutationFn: (v: { blocked_exits?: string[]; attack?: Attack | null; fix?: Fix | null }) =>
      api.post<RunResult>(`/venues/${id}/tier1`, v),
  });
}

export function useSaveSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (values: Record<string, unknown>) => api.put<SettingsOut>("/settings", { values }),
    onSuccess: (data) => qc.setQueryData(qk.settings, data),
  });
}

export function useStartSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { project_id: string; config?: Record<string, unknown> }) => api.post<SessionOut>("/sessions", v),
    onSuccess: (d) => qc.invalidateQueries({ queryKey: qk.sessions(d.project_id) }),
  });
}

export function useStopSession() {
  return useMutation({ mutationFn: (id: string) => api.post<SessionOut>(`/sessions/${id}/stop`) });
}

export function useApplySession(projectId: string) {
  const inv = useInvalidateProject();
  return useMutation({
    mutationFn: (sessionId: string) => api.post<EditResult>(`/sessions/${sessionId}/apply`),
    onSuccess: () => inv(projectId),
  });
}

export function useAsk() {
  return useMutation({
    mutationFn: (v: { project_id: string; run_id?: string | null; question: string;
                      hotspot?: { floor_id: string; x: number; y: number; t_s?: number } | null }) =>
      api.post<AskOut>("/ask", v),
  });
}

/** Designer agent + solver: a description → venue preview (not saved yet). */
/** Documented crowd disasters, rebuilt by the Designer agent from their sourced descriptions. */
export const useRealCases = () =>
  useQuery({ queryKey: ["real_cases"], queryFn: () => api.get<RealCase[]>("/real_cases") });

/** Build a real case's venue (one model call) and start its rule-based test; a case built
 * before opens its project. */
export function useOpenRealCase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<OpenCaseOut>(`/real_cases/${id}/open`, {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["real_cases"] });
      qc.invalidateQueries({ queryKey: qk.projects });
    },
  });
}

export function useDesignVenue() {
  return useMutation({ mutationFn: (text: string) => api.post<VenueDraft>("/venues/design", { text }) });
}

/** A selected building or area on the map → venue preview (not saved yet). */
/** POST /venues/from-map: a building becomes every storey it has; an area records its event. */
export interface FromMapBody {
  outline: [number, number][];
  mode: "indoor" | "outdoor";
  name: string;
  people?: number | null;
  selected_id?: string | null;
  levels?: number | null;
  use?: string | null;
  interior?: "open" | "rooms" | null;
  /** the street and open ground around a building, in metres (G2-06) */
  surroundings_m?: number | null;
  event_kind?: string | null;
}

export function useVenueFromMap() {
  return useMutation({
    mutationFn: (body: FromMapBody) => api.post<VenueDraft>("/venues/from-map", body),
  });
}

// --- Ask or change anything (N15) -----------------------------------------------------------

export type AskIntent = "edit" | "question" | "what_if" | "analyse" | "navigate" | "other";
export type AskTarget = "report" | "expert" | "plan" | "check" | "work";
export type AskScreen = "check" | "plan";
type WhatIfOut = import("./types").WhatIfOut;

/** What-if inputs after the server checked them (scale clamped, exit names matched). */
export interface WhatIfParams {
  crowd_scale: number;
  crowd_scale_asked: number | null;
  capped: boolean;
  weather: "rain" | "smoke" | "none";
  speed_factor: number;
  closed_exits: { id: string; name: string }[];
  changed: boolean;
}
/** The what-if (the /whatif shape) next to the plan as it is: both instant estimates. */
export interface AskWhatIf extends WhatIfOut { before: WhatIfOut; params: WhatIfParams }
/** The explainer's answer (the /ask shape) and the run its numbers come from. */
export interface AskAnswer extends AskOut { run_id: string | null; basis: string }
export type AskAnythingOut = { routed_by: "model" | "keywords" } & (
  | { intent: "edit"; result: EditOut }
  | { intent: "question"; result: AskAnswer }
  | { intent: "what_if"; result: AskWhatIf }
  | { intent: "analyse"; result: AnalyseOut }
  | { intent: "navigate"; result: { target: AskTarget } }
  | { intent: "other"; result: { message: string; examples: string[] } }
);

/** One box for everything. An edit comes back as a proposal: only /patch saves it. */
export function useAskAnything(projectId: string) {
  return useMutation({
    mutationFn: (v: { text: string; context: AskScreen; session_id?: string | null }) =>
      api.post<AskAnythingOut>(`/projects/${projectId}/ask-anything`, v),
  });
}

// --- Autopilot (N13): one request to a tested plan ----------------------------------------

import type { AutopilotRun } from "@/types/generated";

export const autopilotKey = (id: string) => ["autopilot", id] as const;

/** An Autopilot run, polled while it works (its event stream is the fast path). */
export const useAutopilot = (id: string | null | undefined) =>
  useQuery({
    queryKey: autopilotKey(id ?? ""),
    queryFn: () => api.get<AutopilotRun>(`/autopilot/${id}`),
    enabled: !!id,
    retry: (n, e) => (e as { status?: number }).status !== 404 && n < 2,
    refetchInterval: (q) => (q.state.data?.status === "running" || q.state.data?.status === "queued" ? 3000 : false),
  });

/** A project's latest Autopilot run (null when it never had one). */
export const useProjectAutopilot = (projectId: string | undefined) =>
  useQuery({ queryKey: ["project-autopilot", projectId], enabled: !!projectId, retry: false,
             queryFn: () => api.get<AutopilotRun | null>(`/projects/${projectId}/autopilot`) });

/** Plan an event from one sentence (or test a project): returns the run at once. */
export function useStartAutopilot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { text?: string; project_id?: string; depth?: AutopilotRun["depth"] }) =>
      api.post<AutopilotRun>("/autopilot", body),
    onSuccess: (run) => {
      qc.setQueryData(autopilotKey(run.id), run);
      void qc.invalidateQueries({ queryKey: qk.projects });
    },
  });
}

/** Stop gracefully: the plan keeps what was finished. */
export function useStopAutopilot() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<AutopilotRun>(`/autopilot/${id}/stop`),
    onSuccess: (run) => qc.setQueryData(autopilotKey(run.id), run),
  });
}

// --- Your plan: accept the chosen kept fixes (P3-03) ----------------------------------------

import type { ApplyOut } from "./types";

/** Accept a session's kept fixes: all of them (tested together) when `fix_ids` is left out,
 * else only the chosen ones. Updates the project and the session's `applied` record at once,
 * so Your plan never shows the new version as an unexplained change. */
export function useApplyFixes(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { sessionId: string; fix_ids?: string[] }) =>
      api.post<ApplyOut>(`/sessions/${v.sessionId}/apply`, v.fix_ids ? { fix_ids: v.fix_ids } : {}),
    onSuccess: (data, v) => {
      qc.setQueryData<ProjectDetail>(qk.project(projectId), (old) =>
        old ? { ...old, ...data.project, version: data.version, validation: data.validation } : old);
      const record = data.applied;
      if (record) {
        qc.setQueryData<SessionOut>(qk.session(v.sessionId), (old) =>
          old?.summary ? { ...old, summary: { ...old.summary, applied: [...(old.summary.applied ?? []), record] } } : old);
      }
      for (const key of [["plan", projectId], qk.project(projectId), qk.versions(projectId), qk.projects,
        ["countdown", projectId], qk.session(v.sessionId), qk.sessions(projectId)]) {
        void qc.invalidateQueries({ queryKey: key });
      }
    },
  });
}

// --- Crowd analyst and user scripts: code that runs in a sandbox ---------------------------

/** What a code job printed and how it ended (CodeResult on the server). */
export interface CodeRunOut {
  status: "ok" | "error" | "timeout";
  output: unknown;
  stdout_tail: string;
  stderr_tail: string;
  runtime_s: number;
}

/** The analyst's answer: the code it wrote, what it computed, and a number-checked summary. */
export interface AnalyseOut {
  answer: string;
  numbers_checked: boolean;
  status: "ok" | "error" | "timeout" | "rejected";
  code: string;
  plan: string;
  output: unknown;
  runtime_s: number;
  stderr_tail: string;
  problems: string[];
  run_id: string;
  basis: string;
  sandbox: string;
}

/** Ask the analyst about a run (default: the run a question would use). */
export function useAnalyse(projectId: string) {
  return useMutation({
    mutationFn: (v: { question: string; run_id?: string | null; session_id?: string | null }) =>
      api.post<AnalyseOut>(`/projects/${projectId}/analyse`, v),
  });
}

export type UserScriptKind = "analysis" | "scenario";

/** The last run of a saved script: a code job (analysis) or a started simulation (scenario). */
export type UserScriptRun =
  | (CodeRunOut & { run_id: string; sandbox: string; at: string })
  | { status: "started"; run_id: string; at: string };

export interface UserScript {
  id: string;
  name: string;
  kind: UserScriptKind;
  code: string;
  every_s: number;
  author: string;
  created_at: string;
  updated_at: string;
  problems: string[];
  last_run: UserScriptRun | null;
}

export interface UserScriptIn { name: string; kind: UserScriptKind; code: string; every_s: number }

export type RunScriptOut =
  | ({ kind: "analysis" } & CodeRunOut & { run_id: string; sandbox: string; at: string })
  | { kind: "scenario"; status: "started"; run_id: string; at: string; run: RunOut };

const scriptsKey = (projectId: string) => ["scripts", projectId] as const;

export const useScripts = (projectId: string | undefined) =>
  useQuery({
    queryKey: scriptsKey(projectId ?? ""),
    queryFn: () => api.get<{ scripts: UserScript[]; scenario_supported: boolean }>(`/projects/${projectId}/scripts`),
    enabled: !!projectId,
  });

/** Save a new script (no id) or change a saved one. */
export function useSaveScript(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: UserScriptIn & { id?: string | null }) =>
      id ? api.put<UserScript>(`/projects/${projectId}/scripts/${id}`, body)
        : api.post<UserScript>(`/projects/${projectId}/scripts`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: scriptsKey(projectId) }),
  });
}

export function useDeleteScript(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.del<void>(`/projects/${projectId}/scripts/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: scriptsKey(projectId) }),
  });
}

/** Run a saved script in a sandbox. */
export function useRunScript(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: string; run_id?: string | null; tier?: 2 | 3; seed?: number | null }) =>
      api.post<RunScriptOut>(`/projects/${projectId}/scripts/${id}/run`, body),
    onSuccess: (data) => {
      if (data.kind === "scenario") qc.setQueryData(qk.run(data.run.id), data.run);
      return qc.invalidateQueries({ queryKey: scriptsKey(projectId) });
    },
  });
}

// --- Rewind the worst moment and stress test at scale (SANDBOX_SCOPE ideas 3 and 4) ----------

import type { RewindRecord } from "@/journey/plan/rewind";
import type { StressRecord } from "@/journey/plan/stress";

const POLL_MS = 1500;

/** A session's latest rewind (null when none); polled while its branches run. */
export const useRewind = (sessionId: string | null | undefined) =>
  useQuery({ queryKey: ["rewind", sessionId], enabled: !!sessionId,
             queryFn: () => api.get<RewindRecord | null>(`/sessions/${sessionId}/rewind`),
             refetchInterval: (q) => (q.state.data?.status === "running" ? POLL_MS : false) });

/** Rewind the session's worst attack to its moment of peak danger and try every response. */
export function useStartRewind(sessionId: string | null | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<RewindRecord>(`/sessions/${sessionId}/rewind`, {}),
    onSuccess: (rec) => qc.setQueryData(["rewind", sessionId], rec),
  });
}

/** A project's latest stress test at scale (null when none); polled while it runs. */
export const useStress = (projectId: string | undefined) =>
  useQuery({ queryKey: ["stress", projectId], enabled: !!projectId,
             queryFn: () => api.get<StressRecord | null>(`/projects/${projectId}/stress`),
             refetchInterval: (q) => (q.state.data?.status === "running" ? POLL_MS : false) });

export function useStartStress(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { attacks: "session" | "rules"; seeds: number; include_fixes: boolean }) =>
      api.post<StressRecord>(`/projects/${projectId}/stress`, body),
    onSuccess: (rec) => {
      qc.setQueryData(["stress", projectId], rec);
      void qc.invalidateQueries({ queryKey: qk.runs(projectId) });
    },
  });
}

// --- Seed check (S-09): the plan's key run with more seeds ------------------------------------

import type { SeedCheck } from "./types";

export function useSeedCheck(sessionId: string | null) {
  return useQuery({
    queryKey: ["seeds", sessionId],
    enabled: !!sessionId,
    queryFn: () => api.get<SeedCheck>(`/sessions/${sessionId}/seeds`),
    // follow the runs while any is still going
    refetchInterval: (q) => (q.state.data?.status === "running" ? 2500 : false),
  });
}

export function useStartSeedCheck(sessionId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (n?: number) => api.post<SeedCheck>(`/sessions/${sessionId}/seeds`, n ? { n } : {}),
    onSuccess: (d) => qc.setQueryData(["seeds", sessionId], d),
  });
}

// --- How sure the plan's numbers are (P2-04) -----------------------------------------------------
import type { SensitivityRecord, TogetherCheck } from "@/journey/plan/range";
import type { AppliedRecord } from "./types";

export const useSensitivity = (sessionId: string | null | undefined) =>
  useQuery({ queryKey: ["sensitivity", sessionId], enabled: !!sessionId,
             queryFn: () => api.get<SensitivityRecord>(`/sessions/${sessionId}/sensitivity`),
             refetchInterval: (q) => (q.state.data?.status === "running" ? POLL_MS : false) });

export function useStartSensitivity(sessionId: string | null | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<SensitivityRecord>(`/sessions/${sessionId}/sensitivity`, {}),
    onSuccess: (rec) => qc.setQueryData(["sensitivity", sessionId], rec),
  });
}

export interface TogetherOut {
  session_id: string;
  status: "none" | "not_started" | TogetherCheck["status"];
  record: AppliedRecord | null;
}

/** The latest subset version's check; polls while it runs and refreshes the session after. */
export function useTogether(sessionId: string | null | undefined, enabled: boolean) {
  const qc = useQueryClient();
  return useQuery({
    queryKey: ["together", sessionId], enabled: !!sessionId && enabled,
    queryFn: async () => {
      const out = await api.get<TogetherOut>(`/sessions/${sessionId}/together`);
      if (out.status !== "running" && sessionId) void qc.invalidateQueries({ queryKey: qk.session(sessionId) });
      return out;
    },
    refetchInterval: (q) => (q.state.data?.status === "running" ? POLL_MS : false),
  });
}

export function useStartTogether(sessionId: string | null | undefined) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<TogetherOut>(`/sessions/${sessionId}/together`, {}),
    onSuccess: (out) => {
      qc.setQueryData(["together", sessionId], out);
      if (sessionId) void qc.invalidateQueries({ queryKey: qk.session(sessionId) });
    },
  });
}

export interface AgentInfo {
  name: string;
  label: string;
  stage: "build" | "attack" | "defend" | "judge" | "explain";
  decides: string;
  role: string;
  model: string;
  prompt_version: string;
  tools: string[];
}

export interface AgentsOut {
  provider: string;
  agents: AgentInfo[];
  tools: Record<string, string>;
  sandbox: { provider: string; ok: boolean; detail: string; isolation: SandboxIsolation; time_limit_s?: number };
}

/** The AI team (GET /agents): every Nemotron agent, its model, job and tools. */
export function useAgents() {
  return useQuery({ queryKey: ["agents"], queryFn: () => api.get<AgentsOut>("/agents"), staleTime: 60_000 });
}
