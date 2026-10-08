"""Brief agent: one sentence from the organizer → EventBrief (place, crowd, timing, needs)."""

from __future__ import annotations

from datetime import date

from api.agents.base import AgentCall, AgentDef, AgentEnv, call_agent
from api.models.venue_spec import EventBrief

BRIEF_AGENT = AgentDef(
    name="brief",
    role="main",
    prompt_file="event_brief.md",
    output_model=EventBrief,
    temperature=0.1,
    max_tokens=900,
    description="Reads the organizer's request into an event brief.",
)


async def read_brief(env: AgentEnv, text: str, today: date | None = None) -> AgentCall[EventBrief]:
    """Ask the brief agent; the caller falls back to asking the user if it fails."""
    return await call_agent(
        env,
        BRIEF_AGENT,
        {"today": (today or date.today()).isoformat()},
        f'Request: "{text.strip()}"',
        output_model=EventBrief,
        summarize=lambda b: f"{b.kind} for {b.attendees:,} at {b.place or 'a designed venue'}",
    )
