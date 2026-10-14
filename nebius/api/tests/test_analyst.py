"""Crowd analyst: code written by the (fake) model, run by the (fake) sandbox, numbers checked.

No live model and no Docker: FakeLLM plays the analyst, FakeRunner returns scripted outputs.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.adapters.llm import FakeLLM
from api.adapters.sandbox import CodeResult, FakeRunner
from api.agents.analyst import FAILED, FLAGGED, NO_SCRIPT, TIMED_OUT, analyse, run_inputs
from api.agents.base import AgentEnv, AgentUnavailable
from api.agents.router import keyword_intent, route_message
from api.models import Venue
from api.tests.test_api import client as client

SCRIPT = (
    "import showtime_data as sd\n"
    "q = sd.people_near('E1')\n"
    "output = {'facts': {'longest queue (people)': int(q['people'].max())}}\n"
)
OUTPUT = {
    "facts": {"longest queue (people)": 37, "minutes with a queue": 4.5},
    "table": [{"minute": 1, "people": 12}, {"minute": 2, "people": 37}],
    "chart": {"x": "minute", "y": "people", "title": "Queue at Gate B"},
}
FACTS = {"people": 400, "exits": [{"id": "E1", "name": "Gate B"}]}
INPUTS = {"result.json": b"{}"}


def _env(script: dict[str, Any]) -> tuple[AgentEnv, FakeLLM]:
    llm = FakeLLM(script)
    return AgentEnv(llm=llm, audit=False), llm


def _code(code: str = SCRIPT) -> dict[str, str]:
    return {"plan": "Count people within 3 m of Gate B each second.", "code": code}


async def test_the_analyst_writes_code_runs_it_and_quotes_its_numbers(tmp_path: Path) -> None:
    env, llm = _env(
        {
            "analyst": [_code()],
            "analyst_answer": [{"answer": "Up to 37 people queued at Gate B for 4.5 minutes."}],
        }
    )
    runner = FakeRunner(tmp_path, code_results=[CodeResult("ok", OUTPUT, runtime_s=1.2)])
    out = await analyse(env, runner, "How long did people queue at Gate B?", FACTS, INPUTS)
    assert out.status == "ok" and out.numbers_checked
    assert out.answer.startswith("Up to 37 people")
    assert out.output == OUTPUT and out.code == SCRIPT and out.runtime_s == 1.2
    job = runner.code_jobs[0]
    assert job.kind == "analysis" and job.script == SCRIPT and job.inputs == INPUTS
    assert job.timeout_s == 30 and job.job_id.startswith("an-")
    # the answer agent saw the output, not the trajectories
    answer_prompt = next(m for a, m in llm.calls if a == "analyst_answer")[0]["content"]
    assert '"longest queue (people)": 37' in answer_prompt


async def test_a_rejected_script_gets_one_repair_round(tmp_path: Path) -> None:
    env, llm = _env(
        {
            "analyst": [_code("import os\nos.system('x')\n"), _code()],
            "analyst_answer": [{"answer": "Up to 37 people queued."}],
        }
    )
    runner = FakeRunner(tmp_path, code_results=[CodeResult("ok", OUTPUT)])
    out = await analyse(env, runner, "queue at Gate B?", FACTS, INPUTS)
    assert out.status == "ok" and out.code == SCRIPT
    repair = [m for a, m in llm.calls if a == "analyst"][1]
    assert "importing 'os' is not allowed" in repair[-1]["content"]


async def test_a_script_that_stays_unsafe_never_runs(tmp_path: Path) -> None:
    bad = _code("open('/etc/passwd').read()\n")
    env, _ = _env({"analyst": [bad, bad]})
    runner = FakeRunner(tmp_path)
    out = await analyse(env, runner, "queue?", FACTS, INPUTS)
    assert out.status == "rejected" and out.answer == NO_SCRIPT and not out.numbers_checked
    assert runner.code_jobs == []


async def test_a_failing_script_is_fixed_once_with_its_error(tmp_path: Path) -> None:
    fixed = SCRIPT.replace("E1", "Gate B")
    env, llm = _env(
        {
            "analyst": [_code(), _code(fixed)],
            "analyst_answer": [{"answer": "Up to 37 people queued."}],
        }
    )
    runner = FakeRunner(
        tmp_path,
        code_results=[
            CodeResult("error", stderr_tail="KeyError: 'E1'"),
            CodeResult("ok", OUTPUT),
        ],
    )
    out = await analyse(env, runner, "queue?", FACTS, INPUTS)
    assert out.status == "ok" and out.code == fixed
    assert [j.job_id.endswith("-2") for j in runner.code_jobs] == [False, True]
    assert "KeyError: 'E1'" in [m for a, m in llm.calls if a == "analyst"][1][-1]["content"]


async def test_errors_and_timeouts_give_no_numbers(tmp_path: Path) -> None:
    env, llm = _env({"analyst": [_code(), _code()]})
    runner = FakeRunner(tmp_path, code_results=[CodeResult("error", stderr_tail="boom")] * 2)
    out = await analyse(env, runner, "queue?", FACTS, INPUTS)
    assert (out.status, out.answer, out.output) == ("error", FAILED, None)
    env, llm = _env({"analyst": [_code()]})
    runner = FakeRunner(tmp_path, code_results=[CodeResult("timeout", runtime_s=45)])
    out = await analyse(env, runner, "queue?", FACTS, INPUTS)
    assert (out.status, out.answer) == ("timeout", TIMED_OUT)
    assert all(a == "analyst" for a, _ in llm.calls)  # nothing to explain


async def test_invented_numbers_are_regenerated_then_flagged(tmp_path: Path) -> None:
    made_up = {"answer": "About 52 people queued for 9.5 minutes."}
    env, _ = _env({"analyst": [_code()], "analyst_answer": [made_up, {"answer": "37 queued."}]})
    runner = FakeRunner(tmp_path, code_results=[CodeResult("ok", OUTPUT)])
    out = await analyse(env, runner, "queue?", FACTS, INPUTS)
    assert out.numbers_checked and out.answer == "37 queued."  # regenerated

    env, _ = _env({"analyst": [_code()], "analyst_answer": [made_up, made_up]})
    runner = FakeRunner(tmp_path, code_results=[CodeResult("ok", OUTPUT)])
    out = await analyse(env, runner, "queue?", FACTS, INPUTS)
    assert not out.numbers_checked and out.answer == FLAGGED
    assert "52" not in out.answer and out.output == OUTPUT  # the computed results stay


async def test_numbers_from_the_question_may_be_repeated(tmp_path: Path) -> None:
    env, _ = _env(
        {"analyst": [_code()], "analyst_answer": [{"answer": "Within 15 m of Gate B: 37."}]}
    )
    runner = FakeRunner(tmp_path, code_results=[CodeResult("ok", OUTPUT)])
    out = await analyse(env, runner, "how many people within 15 m of Gate B?", FACTS, INPUTS)
    assert out.numbers_checked


async def test_the_model_down_raises(tmp_path: Path) -> None:
    env, _ = _env({})
    with pytest.raises(AgentUnavailable):
        await analyse(env, FakeRunner(tmp_path), "queue?", FACTS, INPUTS)


def test_run_inputs_reads_only_the_artifacts(tmp_path: Path) -> None:
    for name in ("result.json", "traj.bin", "request.json", "progress.json"):
        (tmp_path / name).write_bytes(b"x")
    assert sorted(run_inputs(tmp_path)) == ["result.json", "traj.bin"]


# --- router ----------------------------------------------------------------------------------

ANALYSE = [
    "how long did people queue at South door 1?",
    "how many people left through South door 2",
    "which minute was the worst?",
    "show me a chart of the queue",
    "what was the average time to get out",
]


@pytest.mark.parametrize("text", ANALYSE)
def test_keywords_send_measuring_questions_to_the_analyst(text: str) -> None:
    assert keyword_intent(text) == "analyse"


def test_keywords_keep_what_ifs_and_plain_questions() -> None:
    assert keyword_intent("what if the queue at South door 1 doubles?") == "what_if"
    assert keyword_intent("why is it crowded near the stage?") == "question"


@pytest.mark.parametrize("said", ["analyse", "analysis", "analyze"])
async def test_the_model_may_name_the_intent_loosely(hall: Venue, said: str) -> None:
    env, _ = _env({"router": {"intent": said}})
    route = await route_message(env, hall, "which minute was the worst?")
    assert (route.intent, route.routed_by) == ("analyse", "model")


# --- API -------------------------------------------------------------------------------------


def _new(client: TestClient) -> str:
    r = client.post("/api/v1/projects", json={"template_id": "conference_hall_2f", "name": "H"})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _state(client: TestClient) -> Any:
    return client.app.state.showtime  # type: ignore[attr-defined]


def _simulated_run(client: TestClient, pid: str) -> str:
    """A finished run with its artifacts on disk (the fake runner writes none)."""
    r = client.post("/api/v1/runs", json={"project_id": pid, "tier": 3, "seed": 1})
    assert r.status_code == 202, r.text
    rid = str(r.json()["id"])
    for _ in range(100):
        if client.get(f"/api/v1/runs/{rid}").json()["status"] not in ("queued", "running"):
            break
        time.sleep(0.05)
    run_dir = _state(client).settings.runs_dir / rid
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "result.json").write_text(json.dumps({"run_id": rid}))
    (run_dir / "traj.bin").write_bytes(b"\0" * 8)
    return rid


def test_analyse_needs_a_simulated_run(client: TestClient) -> None:
    pid = _new(client)
    r = client.post(f"/api/v1/projects/{pid}/analyse", json={"question": "queue at Gate B?"})
    assert r.status_code == 409 and r.json()["code"] == "no_run"


def test_analyse_answers_from_code_output(client: TestClient) -> None:
    pid = _new(client)
    rid = _simulated_run(client, pid)
    st = _state(client)
    st.llm.script.update(
        analyst=[_code()], analyst_answer=[{"answer": "Up to 37 people queued at Gate B."}]
    )
    runner: FakeRunner = st.runner
    runner.code_results = [CodeResult("ok", OUTPUT, runtime_s=2.0)]
    r = client.post(f"/api/v1/projects/{pid}/analyse", json={"question": "queue at Gate B?"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["answer"] == "Up to 37 people queued at Gate B." and out["numbers_checked"]
    assert out["output"] == OUTPUT and out["code"] == SCRIPT and out["run_id"] == rid
    assert out["runtime_s"] == 2.0 and out["status"] == "ok" and out["basis"]
    assert sorted(runner.code_jobs[0].inputs) == ["result.json", "traj.bin"]
    system = next(m for a, m in st.llm.calls if a == "analyst")[0]["content"]
    assert '"name": "South door 1"' in system and f'"run_id": "{rid}"' in system


def test_analyse_reports_an_unavailable_model_as_503(client: TestClient) -> None:
    pid = _new(client)
    rid = _simulated_run(client, pid)
    r = client.post(f"/api/v1/projects/{pid}/analyse", json={"question": "queue?", "run_id": rid})
    assert r.status_code == 503 and r.json()["code"] == "llm_unavailable"
    assert _state(client).runner.code_jobs == []  # no fallback analysis


def test_analyse_refuses_a_run_of_another_project(client: TestClient) -> None:
    pid, other = _new(client), _new(client)
    rid = _simulated_run(client, other)
    r = client.post(f"/api/v1/projects/{pid}/analyse", json={"question": "queue?", "run_id": rid})
    assert r.status_code == 409


def test_ask_anything_routes_analyse_questions(client: TestClient) -> None:
    pid = _new(client)
    st = _state(client)
    st.llm.script.update(router={"intent": "analyse"}, explainer={"answer": "It is fine."})
    # nothing simulated yet: answered as a plain question from the instant estimate
    r = client.post(
        f"/api/v1/projects/{pid}/ask-anything", json={"text": "which minute was the worst?"}
    )
    assert r.status_code == 200 and r.json()["intent"] == "question"

    _simulated_run(client, pid)
    st.llm.script.update(analyst=[_code()], analyst_answer=[{"answer": "Minute 2: 37 people."}])
    st.runner.code_results = [CodeResult("ok", OUTPUT)]
    r = client.post(
        f"/api/v1/projects/{pid}/ask-anything", json={"text": "which minute was the worst?"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["intent"] == "analyse" and body["result"]["answer"] == "Minute 2: 37 people."
    assert body["result"]["output"] == OUTPUT


def test_ask_anything_analyse_with_the_model_down_is_a_plain_503(client: TestClient) -> None:
    pid = _new(client)
    _simulated_run(client, pid)
    r = client.post(
        f"/api/v1/projects/{pid}/ask-anything",
        json={"text": "how long did people queue at South door 1?"},
    )
    assert r.status_code == 503
    body = r.json()
    assert body["code"] == "llm_unavailable" and "analysis" in body["message"]
    assert body["details"] == {"intent": "analyse", "routed_by": "keywords"}
