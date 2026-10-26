"""The AI team: every NVIDIA Nemotron agent, what it decides and which tools it may use.

Showtime is a multi-agent system. The agents decide: what the venue is, what could go wrong,
what to change and how to explain it. Deterministic tools do everything that produces a
number: a layout solver turns a design into geometry, the crowd simulator runs every scenario
in a sealed sandbox (Docker locally, Nebius Sandboxes in the cloud), and a number checker
rejects any text that quotes a number the tools did not produce.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from api.agents.analyst import ANALYST_AGENT, ANALYST_ANSWER_AGENT
from api.agents.base import AgentDef
from api.agents.blue_team import BLUE_TEAM_AGENT
from api.agents.event_brief import BRIEF_AGENT
from api.agents.judge import EXPLAINER_AGENT, JUDGE_AGENT
from api.agents.red_team import RED_TEAM_AGENT
from api.agents.router import ROUTER_AGENT
from api.agents.safety_officer import OFFICER_AGENT
from api.agents.venue import VENUE_AGENT
from api.agents.venue_designer import DESIGNER_AGENT
from api.agents.what_if import WHAT_IF_AGENT

Stage = Literal["build", "attack", "defend", "judge", "explain"]
Tool = Literal[
    "simulator",  # JuPedSim crowd simulation in a sealed sandbox
    "instant_estimate",  # network-flow estimate in milliseconds
    "solver",  # layout solver: a design becomes exact geometry
    "map",  # OpenStreetMap sites
    "incidents",  # the real crowd-accident dataset (IncidentSource plugin)
    "search",  # web search for real incidents (a SearchProvider; off without a key)
    "edit_ops",  # validated venue edit operations
    "scenario_events",  # scenario events (blocked exit, surge, smoke, ...)
    "number_check",  # every number in a text must come from the tools
    "code_sandbox",  # the agent's own analysis code, run in a sealed sandbox
]


@dataclass(frozen=True)
class Member:
    """One agent of the team."""

    agent: AgentDef
    label: str  # short, for people
    stage: Stage
    decides: str  # one sentence: what it decides
    tools: tuple[Tool, ...]


TEAM: tuple[Member, ...] = (
    Member(
        BRIEF_AGENT,
        "Brief",
        "build",
        "Reads one sentence about the event: what, where, when, how many.",
        ("map", "search"),
    ),
    Member(
        DESIGNER_AGENT,
        "Designer",
        "build",
        "Designs the venue or building: floors, rooms, stairs, exits and crowd.",
        ("solver",),
    ),
    Member(
        VENUE_AGENT,
        "Editor",
        "build",
        "Turns a typed change into validated edits.",
        ("edit_ops",),
    ),
    Member(ROUTER_AGENT, "Router", "build", "Sends a question or a change to the right agent.", ()),
    Member(
        WHAT_IF_AGENT,
        "What-if planner",
        "attack",
        "Chooses and composes the what-ifs this venue should be tested under.",
        ("scenario_events", "simulator"),
    ),
    Member(
        RED_TEAM_AGENT,
        "Red team",
        "attack",
        "Writes attacks grounded in real disasters, aimed at gaps in the failure map.",
        ("incidents", "search", "scenario_events", "instant_estimate", "simulator"),
    ),
    Member(
        BLUE_TEAM_AGENT,
        "Blue team",
        "defend",
        "Proposes fixes; only those the simulator confirms are kept.",
        ("edit_ops", "scenario_events", "simulator"),
    ),
    Member(
        JUDGE_AGENT,
        "Judge",
        "judge",
        "Writes the final verdict; every number it quotes is checked.",
        ("number_check",),
    ),
    Member(
        OFFICER_AGENT,
        "Safety officer",
        "judge",
        "Lists the actions that matter most, highest priority first.",
        ("number_check",),
    ),
    Member(
        EXPLAINER_AGENT,
        "Explainer",
        "explain",
        "Answers “why is this red?” about a hotspot.",
        ("number_check",),
    ),
    Member(
        ANALYST_AGENT,
        "Analyst",
        "explain",
        "Plans how to answer a question from the run data.",
        ("code_sandbox",),
    ),
    Member(
        ANALYST_ANSWER_AGENT,
        "Analyst (answer)",
        "explain",
        "Answers from the data the analyst gathered.",
        ("number_check",),
    ),
)
