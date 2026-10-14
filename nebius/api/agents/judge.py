"""Judge (final plan text) and Explainer ("Ask the venue"), both number-checked."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from api.agents.base import AgentDef, AgentEnv, audit_decision, call_agent
from api.agents.numbers import allowed_numbers, allowed_times, check_numbers


class JudgeOut(BaseModel):
    """Plain-language conclusion of a red-team session."""

    summary: str = Field(max_length=1200)
    recommendations: list[str] = Field(default_factory=list, max_length=5)


class ExplainOut(BaseModel):
    """Answer to a question about a hotspot."""

    answer: str = Field(max_length=900)


JUDGE_AGENT = AgentDef(
    name="judge",
    role="judge",
    prompt_file="judge.md",
    output_model=JudgeOut,
    temperature=0.1,
    max_tokens=900,
    description="Writes the final plan text; every number is checked.",
)
EXPLAINER_AGENT = AgentDef(
    name="explainer",
    role="main",
    prompt_file="explainer.md",
    output_model=ExplainOut,
    temperature=0.1,
    max_tokens=600,
    description="Answers questions about a hotspot from run data.",
)


# numbers that are part of metric names, not measurements ("evacuation time (95%)")
LABEL_NUMBERS = {95.0}


def _bad_numbers(texts: list[str], facts: Any) -> list[str]:
    allowed = allowed_numbers(facts) | LABEL_NUMBERS
    times = allowed_times(facts)
    bad: list[str] = []
    for t in texts:
        bad.extend(check_numbers(t, allowed, times))
    return bad


async def judge(
    env: AgentEnv,
    facts: dict[str, Any],
    fallback: str,
    *,
    computed_summary: bool = False,
) -> tuple[str, list[str], bool]:
    """Number-check suggestions; session outcome claims use the computed summary.

    Number membership does not validate a causal claim or prove that a fix was accepted.
    Session callers therefore keep their deterministic summary even on valid model output.
    """
    values = {"facts": json.dumps(facts, default=str)[:7000]}

    def validate(out: JudgeOut) -> list[str]:
        bad = _bad_numbers([out.summary, *out.recommendations], facts)
        return [
            f"the number {b} is not in the facts; quote only numbers from the facts"
            for b in bad[:5]
        ]

    call = await call_agent(
        env,
        JUDGE_AGENT,
        values,
        (
            "Suggest follow-up actions. The system computes the outcome summary. "
            "Do not describe fixes as accepted unless they are listed under fixes kept."
            if computed_summary
            else "Write the final assessment."
        ),
        validate=validate,
        summarize=lambda o: (
            f"{len(o.recommendations)} suggestions; outcome summary computed from recorded results"
            if computed_summary
            else o.summary[:200]
        ),
    )
    if call.output is not None and call.ok:
        text = fallback if computed_summary else call.output.summary
        return text, list(call.output.recommendations), True
    audit_decision(
        env, "judge", "template summary used", {"problems": call.problems[:5], "error": call.error}
    )
    return fallback, [], False


async def explain(env: AgentEnv, question: str, context: dict[str, Any]) -> tuple[str, bool]:
    """Answer a question about a hotspot using only the given run data."""
    values = {"context": json.dumps(context, default=str)[:6000]}

    def validate(out: ExplainOut) -> list[str]:
        bad = _bad_numbers([out.answer], context)
        return [f"the number {b} is not in the data" for b in bad[:5]]

    call = await call_agent(
        env,
        EXPLAINER_AGENT,
        values,
        f"Question: {question.strip()[:300]}",
        validate=validate,
        summarize=lambda o: o.answer[:200],
    )
    if call.output is not None and call.ok:
        return call.output.answer, True
    return (
        "I don't know enough to answer that from this run. The data shows the numbers "
        "listed under the hotspot; try asking about density, timing or nearby exits."
    ), False
