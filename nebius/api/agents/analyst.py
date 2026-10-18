"""Crowd analyst: answers a question about a run by writing code that runs in a sandbox.

1. The `analyst` agent (main model) gets the question, the data helper's description and the
   run's facts, and writes a pandas script. `check_analysis` validates it; the model gets one
   repair round for the problems it finds.
2. The script runs with `run_code` (no network, non-root, capped) on the run's artifacts. A
   script that fails gets one more round with its error message.
3. The `analyst_answer` agent explains the output. Its text may quote only numbers the script
   printed (number check, one repair round); otherwise the answer is flagged and replaced.

The LLM never produces a measurement: every number shown comes from the executed code.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from api.adapters.sandbox import CodeJob, CodeResult, SandboxRunner
from api.agents.base import AgentDef, AgentEnv, audit_decision, call_agent
from api.agents.numbers import allowed_numbers, check_numbers
from api.core.analysis_check import MAX_BYTES, check_analysis

INPUT_FILES = (
    "result.json",
    "venue.json",
    "traj.bin",
    "traj_index.json",
    "density.bin",
    "density_index.json",
    "pressure.bin",
    "pressure_index.json",
)
MAX_INPUT_BYTES = 256 * 1024 * 1024
CODE_TIMEOUT_S = 30.0
CODE_MEM = "1g"


class AnalystCode(BaseModel):
    """The script the analyst writes."""

    plan: str = Field(default="", max_length=400)
    code: str = Field(min_length=1, max_length=MAX_BYTES * 2)


class AnalystAnswer(BaseModel):
    """Plain words about what the script computed."""

    answer: str = Field(max_length=900)


ANALYST_AGENT = AgentDef(
    name="analyst",
    role="main",
    prompt_file="analyst.md",
    output_model=AnalystCode,
    temperature=0.1,
    max_tokens=1800,
    description="Writes a pandas script that answers a question about a run (sandboxed).",
)
ANALYST_ANSWER_AGENT = AgentDef(
    name="analyst_answer",
    role="main",
    prompt_file="analyst_answer.md",
    output_model=AnalystAnswer,
    temperature=0.1,
    max_tokens=500,
    description="Explains an analysis output; quotes only numbers the code printed.",
)

NO_SCRIPT = "I couldn't write a safe analysis for that question. Try asking it another way."
FAILED = "The analysis script failed in the sandbox, so I have no computed answer."
TIMED_OUT = "The analysis took too long and was stopped. Try a narrower question."
EMPTY = "The analysis ran but returned no result."
FLAGGED = (
    "The analysis ran. Its written summary quoted numbers the code did not compute, so it is "
    "not shown: read the computed results below."
)


@dataclass
class Analysis:
    """Outcome of one analyst question."""

    answer: str
    numbers_checked: bool
    status: str  # ok | error | timeout | rejected
    code: str = ""
    plan: str = ""
    output: Any = None
    runtime_s: float = 0.0
    stderr_tail: str = ""
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "numbers_checked": self.numbers_checked,
            "status": self.status,
            "code": self.code,
            "plan": self.plan,
            "output": self.output,
            "runtime_s": self.runtime_s,
            "stderr_tail": self.stderr_tail,
            "problems": self.problems,
        }


def run_inputs(run_dir: Path) -> dict[str, bytes]:
    """The run's artifacts that the data helper reads (missing ones are left out)."""
    out: dict[str, bytes] = {}
    total = 0
    for name in INPUT_FILES:
        p = run_dir / name
        if p.is_file():
            size = p.stat().st_size
            if total + size > MAX_INPUT_BYTES:
                continue
            out[name] = p.read_bytes()
            total += size
    return out


def run_facts(result: dict[str, Any], exits: dict[str, str], files: list[str]) -> dict[str, Any]:
    """A compact description of the run for the analyst (ids, totals, what data exists)."""
    m = result.get("metrics") or {}
    return {
        "run_id": result.get("run_id"),
        "people": m.get("agents_total"),
        "evacuated": m.get("agents_evacuated"),
        "evac_time_p95_s": m.get("evac_time_p95_s"),
        "peak_density_ppm2": m.get("peak_density_ppm2"),
        "simulated_s": result.get("sim_time_s"),
        "exits": [{"id": i, "name": n} for i, n in exits.items()],
        "data_available": files,
    }


def _bad_numbers(text: str, data: Any, question: str) -> list[str]:
    allowed = allowed_numbers(data) | allowed_numbers(question)
    return check_numbers(text, allowed)


async def _write(env: AgentEnv, values: dict[str, str], user: str) -> AnalystCode | None:
    call = await call_agent(
        env,
        ANALYST_AGENT,
        values,
        user,
        output_model=AnalystCode,
        validate=lambda o: check_analysis(o.code),
        summarize=lambda o: o.plan[:200] or "analysis script",
    )
    return call.output if call.output is not None and call.ok else None


async def analyse(
    env: AgentEnv,
    runner: SandboxRunner,
    question: str,
    facts: dict[str, Any],
    inputs: dict[str, bytes],
) -> Analysis:
    """Write, check, run and explain an analysis. Raises AgentUnavailable when the LLM is down."""
    q = question.strip()[:500]
    values = {"facts": json.dumps(facts, default=str)[:4000]}
    user = f"Question: {q}"
    script = await _write(env, values, user)
    if script is None:
        audit_decision(env, "analyst", "no safe script", {"question": q})
        return Analysis(NO_SCRIPT, False, "rejected")
    job_id = f"an-{uuid.uuid4().hex[:12]}"
    res = await _run(runner, job_id, script.code, inputs)
    if res.status == "error":  # one round to fix the script with its own error message
        retry = await _write(
            env,
            values,
            f"{user}\n\nYour previous script:\n{script.code[:MAX_BYTES]}\n\nIt failed with:\n"
            f"{res.stderr_tail[-1500:]}\n\nReturn the corrected script.",
        )
        if retry is not None:
            script = retry
            res = await _run(runner, f"{job_id}-2", script.code, inputs)
    _audit(env, q, script, res)
    base = Analysis(
        "",
        False,
        res.status,
        code=script.code,
        plan=script.plan,
        output=res.output,
        runtime_s=res.runtime_s,
        stderr_tail=res.stderr_tail,
    )
    if res.status != "ok":
        base.answer = TIMED_OUT if res.status == "timeout" else FAILED
        return base
    if res.output is None:
        base.answer = EMPTY
        return base
    base.answer, base.numbers_checked = await _explain(env, q, script.plan, res.output)
    return base


async def _run(
    runner: SandboxRunner, job_id: str, code: str, inputs: dict[str, bytes]
) -> CodeResult:
    job = CodeJob(job_id, "analysis", code, inputs, timeout_s=CODE_TIMEOUT_S, mem=CODE_MEM)
    return await runner.run_code(job)


async def _explain(env: AgentEnv, question: str, plan: str, output: Any) -> tuple[str, bool]:
    values = {"output": json.dumps(output, default=str)[:6000], "plan": plan or "(not given)"}

    def validate(out: AnalystAnswer) -> list[str]:
        bad = _bad_numbers(out.answer, output, question)
        return [f"the number {b} is not in the analysis output" for b in bad[:5]]

    call = await call_agent(
        env,
        ANALYST_ANSWER_AGENT,
        values,
        f"Question: {question}",
        output_model=AnalystAnswer,
        validate=validate,
        summarize=lambda o: o.answer[:200],
    )
    if call.output is not None and call.ok:
        return call.output.answer, True
    audit_decision(env, "analyst_answer", "answer flagged", {"problems": call.problems[:5]})
    return FLAGGED, False


def _audit(env: AgentEnv, question: str, script: AnalystCode, res: CodeResult) -> None:
    """Every script, its output and runtime is kept in the audit log."""
    audit_decision(
        env,
        "analyst",
        "analysis ran",
        {
            "question": question,
            "code": script.code,
            "status": res.status,
            "output": json.dumps(res.output, default=str)[:4000],
            "stderr_tail": res.stderr_tail[-1000:],
            "runtime_s": res.runtime_s,
        },
    )
