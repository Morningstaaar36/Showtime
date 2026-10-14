"""Red team script attacks: FakeLLM replies, static validation, rule fallback, session screening.

No script code is ever executed here: the API only parses it.
"""

from __future__ import annotations

from typing import Any

import pytest

from api.adapters.llm import FakeLLM
from api.agents import red_team as red_team_mod
from api.agents.base import AgentEnv
from api.agents.red_team import is_script_attack, red_team
from api.core.extensions import Registry
from api.core.scripts import EXAMPLE_SCRIPT, check_script
from api.models import Venue
from api.orchestrator.fallbacks import rule_attacks
from api.orchestrator.session import SCRIPT_SCREENING
from api.tests.test_redteam import _incidents, _run_session, red_reply, state  # noqa: F401

CROWD_SCRIPT = """
import math
state = {"slowed": False}

def on_step(view, act):
    worst = max(view.zone_ids, key=lambda z: view.zones[z]["density"])
    if not state["slowed"] and view.zones[worst]["density"] > 2.0:
        act.slow_down(0.6)
        act.note(f"Panic spreads from {worst}")
        state["slowed"] = True
"""


def _reply(code: str) -> Any:
    def reply(messages: list[dict[str, str]]) -> dict[str, Any]:
        out = red_reply(messages)
        out["scripts"] = [
            {
                "title": "Panic spreads from the densest zone",
                "incident_row": out["attacks"][0]["incident_row"],
                "code": code,
                "every_s": 2.0,
                "rationale": "Density above 2 people per m² turns into panic.",
            }
        ]
        return out

    return reply


async def test_red_team_returns_a_script_attack(registry: Registry, hall: Venue) -> None:
    llm = FakeLLM({"red_team": _reply(CROWD_SCRIPT)})
    attacks = await red_team(
        AgentEnv(llm=llm, audit=False), registry, hall, None, _incidents(), 3, set()
    )
    scripts = [a for a in attacks if is_script_attack(a)]
    assert len(scripts) == 1
    a = scripts[0]
    ev = a.events[0].model_dump()
    assert ev["type"] == "script" and ev["code"] == CROWD_SCRIPT and ev["every_s"] == 2.0
    assert a.extensions["kind"] == "script"
    assert a.inspired_by.dataset_row == 7 and "E2_nightclub" in str(a.inspired_by.source_url)
    # it survives the same validation every scenario event gets
    spec = registry.event("script")
    spec.params_model.model_validate(ev)
    assert check_script(ev["code"]) == []
    # the prompt documents the view/act API
    prompt = llm.calls[0][1][0]["content"]
    assert "on_step(view, act)" in prompt and "act.close_exit" in prompt


async def test_invalid_script_is_discarded_with_reason(
    registry: Registry, hall: Venue, monkeypatch: pytest.MonkeyPatch
) -> None:
    decisions: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        red_team_mod,
        "audit_decision",
        lambda env, agent, d, details: decisions.append((d, details)),
    )
    bad = "import socket\n\ndef on_step(view, act):\n    open('/etc/passwd')\n"
    llm = FakeLLM({"red_team": _reply(bad)})
    attacks = await red_team(
        AgentEnv(llm=llm, audit=False), registry, hall, None, _incidents(), 3, set()
    )
    assert attacks and not any(is_script_attack(a) for a in attacks)
    dropped = [d for k, d in decisions if k == "discarded script attack"]
    assert dropped
    problems = " ".join(dropped[0]["problems"])
    assert "import of 'socket'" in problems and "'open' is not allowed" in problems


def test_rule_fallback_includes_one_hand_written_script(hall: Venue) -> None:
    out = rule_attacks(hall, None, _incidents(), 3, set())
    scripts = [a for a in out if is_script_attack(a)]
    assert len(scripts) == 1
    assert scripts[0].events[0].model_dump()["code"] == EXAMPLE_SCRIPT
    assert scripts[0].extensions["generated_by"] == "rules"
    assert check_script(EXAMPLE_SCRIPT) == []
    # deterministic de-duplication: the same script is not offered twice
    seen: set[str] = set()
    rule_attacks(hall, None, _incidents(), 3, seen)
    assert not [a for a in rule_attacks(hall, None, _incidents(), 3, seen) if is_script_attack(a)]


async def test_session_sends_script_attacks_straight_to_simulation(state: Any) -> None:  # noqa: F811
    state.llm.script["red_team"] = _reply(CROWD_SCRIPT)
    p = state.projects.create("Hall", template_id="conference_hall_2f")
    row = await _run_session(state, p.id, max_rounds=1)
    assert row.status == "finished"
    events = state.sessions.stored_events(row.id)
    cards = [e.payload for e in events if e.type == "attack_card"]
    scripted = [c for c in cards if c["attack"]["events"][0]["type"] == "script"]
    assert len(scripted) == 1
    assert scripted[0]["screening"] == SCRIPT_SCREENING and scripted[0]["tier1"] == {}
    assert all("screening" not in c for c in cards if c not in scripted)
    atk_id = scripted[0]["attack"]["attack_id"]
    nodes = [e.payload for e in events if e.type == "branch_node"]
    assert any(n.get("node_id") == f"atk:{atk_id}" for n in nodes)
