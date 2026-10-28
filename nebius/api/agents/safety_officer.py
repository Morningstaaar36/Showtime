"""Safety officer agent: prioritised actions from computed facts; every number is checked."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

from api.agents.base import AgentCall, AgentDef, AgentEnv, call_agent
from api.agents.numbers import allowed_numbers, check_numbers

MAX_ACTIONS = 5  # a review short enough to act on


class Action(BaseModel):
    """One recommended action."""

    title: str = Field(max_length=100)
    why: str = Field(max_length=300)
    how: str = Field(max_length=300)
    priority: Literal[1, 2, 3] = 2


class Review(BaseModel):
    """The officer's verdict and actions."""

    summary: str = Field(max_length=300)
    actions: list[Action] = Field(default_factory=list, max_length=MAX_ACTIONS)


OFFICER_AGENT = AgentDef(
    name="officer",
    role="judge",
    prompt_file="safety_officer.md",
    output_model=Review,
    temperature=0.1,
    max_tokens=1200,
    description="Reviews the plan and lists prioritised actions (numbers checked).",
)


def keep_checked(review: Review, facts: dict[str, Any]) -> Review:
    """Drop actions (and a summary) that still quote numbers not found in the facts."""
    allowed = allowed_numbers(facts)
    actions = [
        a for a in review.actions if not check_numbers(f"{a.title} {a.why} {a.how}", allowed)
    ]
    summary = (
        review.summary if not check_numbers(review.summary, allowed) else "Review of the plan."
    )
    return Review(summary=summary, actions=sorted(actions, key=lambda a: a.priority))


async def review_plan(env: AgentEnv, facts: dict[str, Any]) -> AgentCall[Review]:
    """Ask the officer; actions quoting numbers that are not in the facts are sent back once."""
    allowed = allowed_numbers(facts)

    def validate(r: Review) -> list[str]:
        problems = []
        for text in [r.summary, *(f"{a.title} {a.why} {a.how}" for a in r.actions)]:
            bad = check_numbers(text, allowed)
            if bad:
                problems.append(
                    f"These numbers are not in FACTS: {', '.join(bad[:5])}. Use only FACTS."
                )
        return problems[:3]

    return await call_agent(
        env,
        OFFICER_AGENT,
        {"facts": json.dumps(facts, indent=1, ensure_ascii=False), "max_actions": str(MAX_ACTIONS)},
        "Review this plan.",
        output_model=Review,
        validate=validate,
        summarize=lambda r: f"{len(r.actions)} actions: {r.summary[:80]}",
    )
