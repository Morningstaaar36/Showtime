/** TanStack Query hooks for every server resource. */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { PlanSnapshot } from "@/types/generated";
import type {
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
  scene: (id: string, version: number | undefined) => ["scene", id, version ?? "current"] as const,
};

export const useHealth = () =>
  useQuery({ queryKey: qk.health, queryFn: () => api.get<Health>("/health"), refetchInterval: 15000,
             retry: 1 });
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
export function useDesignVenue() {
  return useMutation({ mutationFn: (text: string) => api.post<VenueDraft>("/venues/design", { text }) });
}

/** A selected building or area on the map → venue preview (not saved yet). */
export function useVenueFromMap() {
  return useMutation({
    mutationFn: (body: { outline: [number, number][]; mode: "indoor" | "outdoor"; name: string; people?: number | null; selected_id?: string | null }) =>
      api.post<VenueDraft>("/venues/from-map", body),
  });
}

// --- Ask or change anything (N15) -----------------------------------------------------------

export type AskIntent = "edit" | "question" | "what_if" | "navigate" | "other";
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
