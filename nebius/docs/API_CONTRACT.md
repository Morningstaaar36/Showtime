# API contract: agents, Red Team Night, reports

The web UI and the backend both build against this file. Routes live in
`api/app/routes_agents.py`; types are in `api/models/`. Everything is under `/api/v1`.
Errors always use `{code, message, hint, details}`.

## Text editing (Venue agent)

`POST /projects/{id}/edit`

```json
{"text": "move the stage 10 m back and add a 4 m door on the east wall", "apply": true}
```

Response:

```json
{
  "status": "applied" | "proposed" | "questions" | "failed",
  "patch": {"ops": [...]} | null,
  "questions": ["Which wall do you mean, east or west?"],
  "explanation": "Moved stage 10 m north; added 4 m exit door_e1 on the east wall.",
  "version": { ...version_out... } | null,     // when applied
  "validation": { ok, checks } | null,
  "agent": {"model": "...", "prompt_version": "venue@1", "tokens": 812, "cost_usd": 0.0}
}
```

`apply=false` returns `proposed` without saving (preview in 3D, then the UI sends
`POST /projects/{id}/patch`).

## Red Team Night sessions

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/sessions` | start: `{project_id, config?: {max_rounds, attacks_per_round, fixes_per_attack, seed, confirm_tier3: true}}` → session |
| GET | `/sessions/{id}` | session row: `{id, project_id, venue_version, status, config, summary, tokens, cost_usd, created_at, finished_at, error}` |
| GET | `/projects/{id}/sessions` | list (newest first) |
| GET | `/sessions/{id}/events?after=<seq>` | SSE stream; every message `data:` is a SessionEvent JSON; replays from `after` (default 0) then streams live; ends with an `event: end` message when the session is finished |
| POST | `/sessions/{id}/stop` | stop gracefully (finishes with partial results) |
| POST | `/sessions/{id}/apply` | save the session's final fixed venue as a new project version; body `{fix_ids?}` accepts only some kept fixes, and then starts simulating them together (`applied.together`) |
| GET / POST | `/sessions/{id}/together` | the latest subset version's run of its fixes together: `status` `none`, `not_started`, `running`, `done` (simulated; `record.together.evaluation`), `preview` (mock sandbox) or `failed`; POST starts it again (409 `together_unavailable` without a subset) |
| GET / POST | `/sessions/{id}/sensitivity` | the plan's key run with 20% fewer/more people and walking 15% slower/faster: each run with basis and `breaks`, `range` over finished runs, `holds_in_all`, `breaks_in`, `notes`; POST starts it (202; 409 `sensitivity_unavailable` before the test finished) |
| GET | `/sessions/{id}/report` | printable HTML report (Exporter `export_html_report`) |
| GET | `/sessions/{id}/map.svg` | evacuation map (Exporter `export_svg_map`) |
| GET | `/sessions/{id}/bundle.json` | everything as JSON (Exporter `export_json_bundle`) |
| GET | `/projects/{id}/report` | report for the latest stress test without a session |

`summary` (when finished):

```json
{
  "baseline_run_id": "r_…", "final_run_id": "r_…" | null,
  "scoreboard": [{"round": 1, "breaks": 3, "attacks": 5}, {"round": 2, "breaks": 1, "attacks": 4}],
  "accepted_fixes": ["F1", "F3"], "attacks": [Attack...], "fixes": [Fix...],
  "worst_attack_id": "A2",
  "before": {"evac_time_p95_s": 412, "peak_density_ppm2": 6.1, "time_above_danger_s": 95},
  "after":  {"evac_time_p95_s": 298, "peak_density_ppm2": 4.2, "time_above_danger_s": 0},
  "judge_text": "…every number checked against results…",
  "countdown": Countdown | null,
  "stopped_reason": "no new breaks" | "budget: tokens" | "budget: rounds" | "stopped by user" | …
}
```

### SessionEvent (`api/models/session.py`)

`{seq, type, ts, payload}`. Payload by type:

| type | payload |
| --- | --- |
| `status` | `{status: "running"\|"finished"\|"stopped"\|"failed", phase: "baseline"\|"red_team"\|"screening"\|"simulating"\|"blue_team"\|"confirming"\|"judging"\|"done", round, message}` |
| `agent_call` | `{agent, role, model, prompt_version, tokens_in, tokens_out, cost_usd, ms, ok, summary, repaired}` |
| `tool_call` | `{tool, args, summary}` (search_web, run_tier1, run_sim, get_forecast, incidents) |
| `attack_card` | `{round, attack: Attack, tier1: {evac_time_p95_s, peak_density_ppm2}, rank}` |
| `fix_card` | `{round, fix: Fix, attack_id}` |
| `run_started` | `{run_id, tier, label, attack_id, fix_id, parent_run_id}` |
| `run_finished` | `{run_id, status, tier, metrics: {evac_time_p95_s, peak_density_ppm2, time_above_danger_s, agents_not_evacuated}, is_break, break_reasons: ["peak density 6.1 ≥ 5", …], accepted?: bool}` |
| `branch_node` | `{node_id, parent_id, kind: "baseline"\|"attack"\|"fix"\|"final", label, run_id, status: "pending"\|"running"\|"break"\|"ok"\|"failed"\|"rejected", metrics?, attack_id?, fix_id?, accepted?}` (re-sent with the same node_id when the status changes) |
| `score` | `{round, breaks, attacks_tested, fixes_accepted, scoreboard: [{round, breaks, attacks}]}` |
| `cost` | `{tokens_total, cost_usd, by_role: {fast, main, …}, budget_tokens}` |
| `countdown` | `{countdown: Countdown}` |
| `marshal` | `{run_id, t_s, x, y, floor_id, speech}` |
| `log` | `{level: "info"\|"warning"\|"error", message}` |

`is_break` (section 12.1): `time_above_danger_s ≥ DANGER_MIN_DURATION_S` (default 5 s), or
`trapped > 0`, or `agents_not_evacuated > max(5, 0.5 % of people)`, or
`RSET × SAFETY_FACTOR + PRE_MOVEMENT_S > available time` when a hazard time exists.

## Ask the venue (Explainer agent)

`POST /ask`

```json
{"project_id": "p_…", "run_id": "r_…", "question": "Why is this red?",
 "hotspot": {"floor_id": "F0", "x": 31.5, "y": 1.5, "t_s": 54}}
```

Response:

```json
{"answer": "…numbers quoted from the run…", "camera_target": {"floor_id": "F0", "x": 31.5, "y": 1.5},
 "sources": [{"title": "…", "url": "https://…"}], "numbers_checked": true,
 "context": {"peak_density_ppm2": 5.4, "nearby_exits": [...], "flows": [...]},
 "agent": {"model": "…", "tokens": 640}}
```

The answer says "I don't know" when the run has no data for the question.
