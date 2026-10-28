"""Bring your own model: scripts an organizer or engineer writes, saved per project.

- An analysis script uses the same data helper as the analyst (`showtime_data`) and runs as
  a code job (`run_code`) on a run's artifacts.
- A scenario script uses the `script` event API (`on_step(view, act)`) and runs as a quick
  simulation with a `script` event, through the same path as POST /runs.

Scripts are stored with author "you" in the internal key-value table (`_scripts:<project>`),
with their last run (status, output, tails, runtime, run id). No database migration.
"""

from __future__ import annotations

import ast
import importlib
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from api.adapters.sandbox import CodeJob
from api.agents.analyst import run_inputs
from api.app.errors import ApiException
from api.app.routes_ask import analysis_run
from api.app.routes_core import get_state
from api.app.routes_runs import RunIn, start_run
from api.app.state import AppState
from api.core.analysis_check import MAX_BYTES, check_analysis
from api.db.models import UserSetting
from api.db.session import db_session
from api.models import ScenarioEventIn

router = APIRouter(prefix="/api/v1")
ScriptKind = Literal["analysis", "scenario"]
SCRIPT_EVENT = "script"


class ScriptIn(BaseModel):
    """A script to save. `every_s` is how often a scenario script's on_step runs."""

    name: str = Field(min_length=1, max_length=80)
    kind: ScriptKind
    code: str = Field(min_length=1, max_length=MAX_BYTES * 2)
    every_s: float = Field(default=1.0, gt=0, le=60)


class RunScriptIn(BaseModel):
    """Where to run a script: the run an analysis reads, the tier and seed of a scenario."""

    run_id: str | None = None
    session_id: str | None = None
    tier: Literal[2, 3] = 2
    seed: int | None = None


def _key(project_id: str) -> str:
    return f"_scripts:{project_id}"


def _load(st: AppState, project_id: str) -> list[dict[str, Any]]:
    with db_session(st.projects.db_url) as s:
        row = s.get(UserSetting, _key(project_id))
        value = row.value if row is not None else None
    items = value.get("scripts") if isinstance(value, dict) else None
    return [dict(x) for x in items] if isinstance(items, list) else []


def _save(st: AppState, project_id: str, scripts: list[dict[str, Any]]) -> None:
    with db_session(st.projects.db_url) as s:
        row = s.get(UserSetting, _key(project_id)) or UserSetting(key=_key(project_id))
        row.value = {"scripts": scripts}
        s.add(row)
        s.commit()


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def scenario_supported(st: AppState) -> bool:
    """True when the simulator has the `script` event (scenario scripts can run)."""
    return bool(st.registry.has("ScenarioEvent", SCRIPT_EVENT))


def _scenario_problems(code: str) -> list[str]:
    """The shared scenario pre-check when it exists, else a syntax and on_step check."""
    try:
        check = importlib.import_module("api.core.scripts").check_script
    except (ImportError, AttributeError):
        check = None
    if check is not None:
        out = check(code)
        items = getattr(out, "problems", out)
        if isinstance(items, list | tuple):
            return [str(getattr(p, "message", p)) for p in items]
        return [] if out in (None, True) else ["The script did not pass the scenario check."]
    size = len(code.encode())
    if size > MAX_BYTES:
        return [f"The script is {size} bytes; the limit is {MAX_BYTES} (8 KB)."]
    try:
        tree = ast.parse(code, filename="script.py")
    except SyntaxError as exc:
        return [f"Syntax error on line {exc.lineno}: {exc.msg}."]
    if not any(isinstance(n, ast.FunctionDef) and n.name == "on_step" for n in tree.body):
        return ["A scenario script needs a function on_step(view, act)."]
    return []


def problems_of(kind: ScriptKind, code: str) -> list[str]:
    """Pre-check problems in plain words (empty list = the script may run)."""
    return check_analysis(code) if kind == "analysis" else _scenario_problems(code)


def _find(scripts: list[dict[str, Any]], script_id: str) -> dict[str, Any]:
    for s in scripts:
        if s.get("id") == script_id:
            return s
    raise ApiException(404, "not_found", "There is no saved script with that id.")


@router.get("/projects/{project_id}/scripts")
def list_scripts(project_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """The project's scripts, newest change first."""
    st.projects.get(project_id)
    scripts = sorted(_load(st, project_id), key=lambda s: s.get("updated_at", ""), reverse=True)
    return {"scripts": scripts, "scenario_supported": scenario_supported(st)}


@router.post("/projects/{project_id}/scripts", status_code=201)
def create_script(
    project_id: str, body: ScriptIn, st: AppState = Depends(get_state)
) -> dict[str, Any]:
    """Save a new script; problems found by the pre-check are returned and block running."""
    st.projects.get(project_id)
    scripts = _load(st, project_id)
    if len(scripts) >= st.settings.max_scripts_per_project:
        raise ApiException(
            422,
            "too_many_scripts",
            f"A project keeps at most {st.settings.max_scripts_per_project} scripts.",
            "Delete one you no longer need.",
        )
    now = _now()
    item = {
        "id": f"s_{uuid.uuid4().hex[:10]}",
        "name": body.name.strip(),
        "kind": body.kind,
        "code": body.code,
        "every_s": body.every_s,
        "author": "you",
        "created_at": now,
        "updated_at": now,
        "problems": problems_of(body.kind, body.code),
        "last_run": None,
    }
    _save(st, project_id, [*scripts, item])
    return item


@router.put("/projects/{project_id}/scripts/{script_id}")
def update_script(
    project_id: str, script_id: str, body: ScriptIn, st: AppState = Depends(get_state)
) -> dict[str, Any]:
    """Change a saved script (its last run is kept until it runs again)."""
    st.projects.get(project_id)
    scripts = _load(st, project_id)
    item = _find(scripts, script_id)
    item.update(
        name=body.name.strip(),
        kind=body.kind,
        code=body.code,
        every_s=body.every_s,
        updated_at=_now(),
        problems=problems_of(body.kind, body.code),
    )
    _save(st, project_id, scripts)
    return item


@router.delete("/projects/{project_id}/scripts/{script_id}", status_code=204)
def delete_script(project_id: str, script_id: str, st: AppState = Depends(get_state)) -> Response:
    """Remove a saved script."""
    st.projects.get(project_id)
    scripts = _load(st, project_id)
    _find(scripts, script_id)
    _save(st, project_id, [s for s in scripts if s.get("id") != script_id])
    return Response(status_code=204)


@router.post("/projects/{project_id}/scripts/{script_id}/run")
async def run_script(
    project_id: str, script_id: str, body: RunScriptIn, st: AppState = Depends(get_state)
) -> dict[str, Any]:
    """Run a saved script in a sandbox: analysis → code job; scenario → quick simulation."""
    st.projects.get(project_id)
    item = _find(_load(st, project_id), script_id)
    problems = problems_of(item["kind"], item["code"])
    if problems:
        raise ApiException(
            422,
            "script_invalid",
            problems[0],
            "Fix the script and run it again.",
            {"problems": problems},
        )
    if item["kind"] == "analysis":
        last = await _run_analysis(st, project_id, item, body)
        out: dict[str, Any] = {"kind": "analysis", **last}
    else:
        run = await _run_scenario(st, project_id, item, body)
        last = {"status": "started", "run_id": run["id"], "at": _now()}
        out = {"kind": "scenario", **last, "run": run}
    scripts = _load(st, project_id)  # reload: the run may have taken a while
    try:
        _find(scripts, script_id)["last_run"] = last
        _save(st, project_id, scripts)
    except ApiException:  # deleted meanwhile: the result is still returned
        pass
    return out


async def _run_analysis(
    st: AppState, project_id: str, item: dict[str, Any], body: RunScriptIn
) -> dict[str, Any]:
    venue = st.projects.venue(project_id)
    row = analysis_run(st, project_id, venue, body.run_id, body.session_id)
    if row is None:
        raise ApiException(
            409,
            "no_run",
            "There is no simulated run for this script to read yet.",
            "Run a stress test first; analysis scripts read its crowd movements.",
        )
    inputs = await run_in_threadpool(run_inputs, st.settings.runs_dir / row.id)
    job = CodeJob(
        f"us-{uuid.uuid4().hex[:12]}",
        "user_script",
        item["code"],
        inputs,
        timeout_s=st.settings.code_timeout_s,
        mem=st.settings.code_mem,
    )
    res = await st.runner.run_code(job)
    return {**res.to_dict(), "run_id": row.id, "sandbox": st.runner.provider, "at": _now()}


async def _run_scenario(
    st: AppState, project_id: str, item: dict[str, Any], body: RunScriptIn
) -> dict[str, Any]:
    if not scenario_supported(st):
        raise ApiException(
            422,
            "scenario_unsupported",
            "Scenario scripts need the simulator's script event, which isn't installed yet.",
            "Analysis scripts work already.",
        )
    event = ScenarioEventIn.model_validate(
        {
            "type": SCRIPT_EVENT,
            "at_s": 0,
            "title": item["name"],
            "code": item["code"],
            "every_s": item.get("every_s", 1.0),
        }
    )
    run_in = RunIn(
        project_id=project_id,
        tier=body.tier,
        seed=body.seed,
        events=[event],
        label=f"Script: {item['name']}"[:120],
    )
    return await start_run(run_in, st)
