/** Response shapes of the HTTP routes (api/app/routes_*.py). Contracts come from generated.ts. */
import type {
  Attack,
  Check,
  Countdown,
  EvidenceReference,
  Fix,
  HazardResult,
  InputProvenance,
  PatchOpIn,
  RunResult,
  SceneObject,
  SceneSnapshot,
  SessionEvent,
  StageCheckResult,
  StageParams,
  Venue,
  VenuePatch,
} from "@/types/generated";
import type { TogetherCheck } from "@/journey/plan/range";
import type { CostRecord, Evaluation } from "@/lib/evidence";
import type { MapConfig } from "@/state/mapConfig";

export type {
  Attack,
  Check,
  Countdown,
  Fix,
  HazardResult,
  InputProvenance,
  PatchOpIn,
  RunResult,
  SceneObject,
  SceneSnapshot,
  SessionEvent,
  StageCheckResult,
  StageParams,
  Venue,
  VenuePatch,
};
export type Floor = Venue["floors"][number];
export type Exit = Floor["exits"][number];
export type Zone = Floor["zones"][number];
export type Obstacle = Floor["obstacles"][number];
export type Stair = NonNullable<Venue["stairs"]>[number];
export type Hotspot = NonNullable<RunResult["hotspots"]>[number];
export type Pt = [number, number];
/** Patch as sent by the UI (server fills schema_version). */
export interface PatchInput {
  ops: PatchOpIn[];
}

/** POST /projects/{id}/patch/preview: the venue a patch would produce, nothing saved. */
export interface PatchPreview {
  ok: boolean;
  base_version: number;
  problems: string[];
  venue: Venue | null;
  validation?: Validation;
  warnings?: Check[];
}

export interface ProjectSummary {
  id: string;
  name: string;
  description: string;
  thumb?: Venue;
  template_id: string | null;
  current_version: number;
  can_undo: boolean;
  can_redo: boolean;
  sample: boolean;
  created_at: string;
  updated_at: string;
  mode: "indoor" | "outdoor";
  people: number;
  floors: number;
  exits: number;
  venue_name: string;
}

export interface Validation {
  ok: boolean;
  checks: Check[];
  rules?: RuleRow[];
}

interface RuleRow {
  rule_id: string;
  status: "pass" | "fail" | "unknown";
  message: string;
  metric: string;
  value?: number | null;
  limit?: number | null;
  unit?: string;
  source_url?: string | null;
  target_id?: string | null;
  confirmed?: boolean;
  pack?: string;
}

export interface VersionOut {
  version: number;
  message: string;
  author: string;
  created_at: string;
  venue_hash: string;
  plan_hash?: string;
  base_version: number | null;
  patch: VenuePatch | null;
  venue?: Venue;
}

export interface ProjectDetail extends ProjectSummary {
  version: VersionOut & { venue: Venue };
  validation: Validation;
}

export interface EditResult {
  project: ProjectSummary;
  version: VersionOut & { venue: Venue };
  validation: Validation;
  warnings?: Check[];
}

interface RunProgress {
  floor_id?: string;
  sim_time_s: number;
  agents_remaining: number;
  agents_total: number;
  wall_s: number;
}

export interface RunOut {
  id: string;
  project_id: string | null;
  session_id: string | null;
  venue_version: number | null;
  tier: number;
  status: "queued" | "running" | "ok" | "partial" | "timeout" | "failed" | "cancelled";
  label: string;
  attack_id: string | null;
  fix_id: string | null;
  parent_run_id: string | null;
  result: RunResult | null;
  progress: RunProgress | null;
  error: string | null;
  created_at: string;
  finished_at: string | null;
  tier1?: RunResult | null;
  evidence?: EvidenceReference;
}

export interface Template {
  id: string;
  name: string;
  description: string;
  mode: "indoor" | "outdoor";
  people: number;
  floors: number;
  exits: number;
  venue: Venue;
}

/** What a sandbox guarantees for every run (GET /health → providers.sandbox.isolation). */
export interface SandboxIsolation {
  kind: "container" | "cloud" | "none";
  network_off: boolean | null;
  memory: string | null;
  cpus: number | null;
  read_only: boolean;
  process_limit: number | null;
  non_root: boolean;
  per_job_limits: boolean;
  summary: string;
}

export interface ProviderStatus {
  ok: boolean;
  detail: string;
  provider?: string;
  label?: string;
  live?: boolean;
  models?: Record<string, string>;
  isolation?: SandboxIsolation;
  time_limit_s?: number;
  /** what the provider is, in plain words ("Nebius Token Factory", "Local Docker") */
  title?: string;
  /** the AI runs on a hosted service (model ids and prices apply) */
  is_cloud?: boolean;
  /** "<title> is not configured: set X in .env." when a requirement is missing */
  not_configured?: string | null;
  capabilities?: Record<string, boolean>;
  /** how many runs the sandbox takes at once */
  parallel?: number;
  /** model ids the AI provider does not serve (checked at startup) */
  model_warnings?: string[];
  /** why this sandbox stands in for the one chosen (it is not configured yet) */
  fallback?: string | null;
}

interface PluginRow {
  id: string;
  name: string;
  version: string;
  enabled: boolean;
  healthy: boolean;
  error: string | null;
  provides: string[];
  registered?: string[];
  source?: string;
}

export interface Health {
  ok: boolean;
  providers: {
    llm: ProviderStatus;
    sandbox: ProviderStatus;
    search: ProviderStatus;
    weather: ProviderStatus;
  };
  plugins: PluginRow[];
  /** how long the web app waits for a read and a write (server settings) */
  client?: { read_timeout_s: number; write_timeout_s: number; map?: MapConfig };
  version: string;
}

interface EventSpec {
  type: string;
  label: string;
  description: string;
}

export interface Features {
  plugins: Record<string, boolean>;
  patch_ops: string[];
  events: EventSpec[];
  hazards: string[];
  exporters: { id: string; label: string; media_type: string; file_ext: string }[];
  importers: { id: string; label: string; file_extensions: string[] }[];
  rules: string[];
  incidents: { id: string; label: string; count: number }[];
  search_live: boolean;
  provider: string;
}

/** A setting, or a table of them (`editor`, `speed_presets`). */
export type SettingValue = number | string | boolean | Record<string, number>;

export interface SettingsOut {
  effective: Record<string, SettingValue>;
  ui: Record<string, unknown>;
  defaults: Record<string, SettingValue>;
}

export interface CountdownOut {
  countdown: Countdown;
  hazards: HazardResult[];
  errors: string[];
  manual_input_needed: boolean;
  timezone: string;
}

export interface EditOut {
  status: "applied" | "proposed" | "questions" | "failed";
  patch: VenuePatch | null;
  questions: string[];
  explanation: string;
  version: (VersionOut & { venue: Venue }) | null;
  validation: Validation | null;
  agent?: { model: string; prompt_version: string; tokens: number; cost_usd: number };
}

export interface SessionOut {
  id: string;
  project_id: string;
  venue_version: number;
  status: "queued" | "running" | "finished" | "stopped" | "failed";
  config: Record<string, unknown>;
  summary: SessionSummary | null;
  tokens: number;
  cost_usd: number;
  created_at: string;
  finished_at: string | null;
  error: string | null;
}

interface SessionSummary {
  baseline_run_id?: string;
  final_run_id?: string | null;
  scoreboard?: { round: number; breaks: number; attacks: number }[];
  accepted_fixes?: string[];
  attacks?: Attack[];
  fixes?: Fix[];
  worst_attack_id?: string;
  before?: Record<string, number | null>;
  after?: Record<string, number | null>;
  judge_text?: string;
  recommendations?: string[];
  numbers_checked?: boolean;
  /** agents whose part built-in rules played because the model didn't answer: agent -> why */
  stood_in?: Record<string, string>;
  countdown?: Countdown | null;
  stopped_reason?: string;
  /** what the results show (absent in sessions saved before evaluations existed) */
  evaluation?: Evaluation | null;
  /** measured model and compute usage of the session */
  cost?: CostRecord | null;
  /** one record per version saved from this session's kept fixes */
  applied?: AppliedRecord[];
}

/** A version saved by POST /sessions/{id}/apply: which kept fixes it holds and whether they
 * were tested together (every kept fix, or a subset once its own run has finished). */
export interface AppliedRecord {
  version: number;
  plan_hash: string;
  fix_ids: string[];
  tested_together: boolean;
  note: string | null;
  at: string;
  /** a subset's run of the chosen fixes together (absent when every kept fix was accepted) */
  together?: TogetherCheck | null;
}

/** POST /sessions/{id}/apply */
export interface ApplyOut extends EditResult {
  applied: AppliedRecord | null;
}

export interface AskOut {
  answer: string;
  camera_target: { floor_id: string; x: number; y: number } | null;
  sources: { title: string; url: string }[];
  numbers_checked: boolean;
  context?: Record<string, unknown>;
}

export interface GlossaryItem {
  term: string;
  definition: string;
}

/** A generated venue awaiting "Create project" (from a description or the map). */
export interface VenueDraft {
  status: "built" | "needs_fixes" | "failed";
  venue?: Venue;
  notes: string[];
  assumptions: string[];
  problems: string[];
  checks?: { code: string; severity: "error" | "warning" | "info"; message: string; hint?: string }[];
  model?: string;
  attribution?: string;
}

/** OpenStreetMap search hit. `outline` and `bbox` are [lat, lon]. */
export interface Place {
  name: string;
  display_name: string;
  lat: number;
  lon: number;
  bbox: [number, number, number, number]; // south, west, north, east
  kind: string;
  outline: [number, number][] | null;
}

/** OpenStreetMap feature (coords are [lat, lon]). */
export interface OsmFeature {
  id: string;
  kind: "building" | "area" | "path" | "barrier" | "entrance" | "water";
  name: string;
  tags: Record<string, string>;
  coords: [number, number][];
  closed: boolean;
  /** buildings (GET /places/at): storeys the map lists and the use its tags suggest */
  levels?: number | null;
  use?: string | null;
}

/** Organizer estimates (GET /projects/{id}/estimates): planning ratios + instant egress model. */
interface EstimateLine { key: string; label: string; value: number; unit: string; detail: string; source: string; url: string; status: "ok" | "warn" | "info" }
interface BudgetLine { item: string; quantity: number; unit: string; unit_cost: number; total: number }
export interface Estimates {
  event: { duration_h: number; alcohol: boolean; audience: "standing" | "seated" | "mixed"; kind?: string };
  capacity: { safe_people: number; by_space: number; by_egress: number | null; limited_by: "space" | "exits" | "stairs"; usable_area_m2: number; density_ppm2: number; target_evac_s: number; current_people: number; note: string };
  lines: EstimateLine[];
  budget: BudgetLine[];
  budget_total: number;
  currency: string;
  prices_are_examples: boolean;
  disclaimer: string;
}

/** Planning score (POST /projects/{id}/whatif): five weighted parts, each explained. */
interface ScorePart { key: string; label: string; score: number; weight: number; detail: string }
export interface PlanScore { score: number; grade: "A" | "B" | "C" | "D" | "F"; parts: ScorePart[]; capped: string; basis: string }
export interface WhatIfOut {
  metrics: RunResult["metrics"];
  hotspots: Hotspot[];
  capacity: Estimates["capacity"];
  lines: EstimateLine[];
  budget_total: number;
  currency: string;
  score: PlanScore;
  basis: string;
  people: number;
}

/** GET /validation: simulator vs a real bottleneck experiment (api/models/validation.py). */
interface ValidationSeedRun {
  seed: number;
  run_id: string;
  flow_ps: number;
  crossings: number;
  window_s: number[];
}

interface ValidationWidth {
  run_name: string;
  b_m: number;
  l_m: number;
  n_people: number;
  measured_flow_ps: number;
  measured_specific_flow: number;
  measured_window_s: number[];
  simulated_flow_ps: { median: number; min: number; max: number; runs: ValidationSeedRun[] };
  simulated_specific_flow: number;
  error_pct: number;
}

export interface SimulatorValidation {
  schema_version: number;
  meta: {
    dataset: string;
    dataset_doi: string;
    dataset_licence: string;
    funding: string;
    papers: { label: string; url: string }[];
    method: string;
    measurement_line: string;
    steady_window: string;
    engine: string;
    model: string;
    pedpy_version: string;
    sim_image: string;
    agent_radius_m: number;
    walk_speed: string;
    sim_dt_s: number;
    frame_hz: number;
    seeds: number[];
    app_defaults: boolean;
    generated_at: string;
    assumptions: string[];
    experimental_repeat: string;
  };
  widths: ValidationWidth[];
  median_abs_error_pct: number;
  mean_error_pct: number;
}

/** GET/POST /sessions/{id}/seeds: the plan's key run repeated with more seeds. */
export interface SeedSpread { min: number; max: number; median: number; n: number }
interface SeedItem {
  seed: number;
  run_id: string | null;
  original: boolean;
  status: string;
  basis: string;
  tier: number | null;
  progress: number | null;
  metrics: { evac_time_p95_s: number | null; peak_density_ppm2: number; agents_not_evacuated: number; agents_total?: number; time_above_danger_s?: number } | null;
  error: string | null;
  included: boolean;
}
export interface SeedCheck {
  session_id: string;
  available: boolean;
  reason: string | null;
  key: { side: "after" | "baseline"; run_id: string; label: string; tier: number; seed: number; attack_title: string | null } | null;
  default_extra: number;
  max_extra: number;
  status: "none" | "running" | "done";
  n_extra: number;
  items: SeedItem[];
  done: number;
  total: number;
  range: Record<"evac_time_p95_s" | "peak_density_ppm2" | "agents_not_evacuated", SeedSpread | null> | null;
  bases: Record<string, number>;
  notes: string[];
}
