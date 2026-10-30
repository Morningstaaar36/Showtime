"""Quick runs last as long as the building needs, simulations run side by side, and an
organizer can redesign a venue with their own words."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from api.adapters.llm import FakeLLM
from api.adapters.sandbox import _acquire_slot, _release_lock
from api.core.extensions import Registry
from api.core.settings import Settings
from api.models import RunMetrics, RunResult
from api.orchestrator import redesign
from api.orchestrator.runs import quick_horizon
from api.tests.test_design_loop import FakeOsm, _spec


def _t1(evac_s: float | None) -> RunResult:
    return RunResult(run_id="t1", tier=1, status="ok", metrics=RunMetrics(evac_time_max_s=evac_s))


def test_a_quick_run_lasts_as_long_as_the_building_needs() -> None:
    s = Settings(_env_file=None, tier2_max_sim_s=180, tier2_horizon_factor=1.6, max_sim_s=900)
    assert quick_horizon(s, _t1(60)) == 180  # small venue: the usual quick run
    assert quick_horizon(s, _t1(200)) == 330  # 320 s, rounded up to 30 s steps
    assert quick_horizon(s, _t1(2000)) == 900  # never past the full limit
    assert quick_horizon(s, _t1(None)) == 180


def test_simulation_slots_let_that_many_run_at_once(tmp_path: Path) -> None:
    held = [_acquire_slot(tmp_path, 2), _acquire_slot(tmp_path, 2)]
    got: list[Any] = []
    t = threading.Thread(target=lambda: got.append(_acquire_slot(tmp_path, 2)))
    t.start()
    time.sleep(0.6)
    assert not got, "a third simulation waits while two run"
    _release_lock(held[0])
    t.join(timeout=5)
    assert got, "it starts as soon as a slot is free"
    for fh in [held[1], *got]:
        _release_lock(fh)


class _Projects:
    def __init__(self, venue: Any) -> None:
        self.saved: list[tuple[Any, str]] = []
        self._venue = venue

    def venue(self, project_id: str) -> Any:
        return self._venue

    def replace_venue(self, project_id: str, venue: Any, message: str, author: str = "") -> Any:
        self.saved.append((venue, message))
        return SimpleNamespace(version=2)


async def test_an_organizer_redesigns_a_described_venue_in_their_own_words(
    registry: Registry,
) -> None:
    from api.agents.base import AgentEnv
    from api.orchestrator.designing import design_from_text

    st0 = SimpleNamespace(
        registry=registry, settings=Settings(_env_file=None, design_rounds=1), osm=FakeOsm(None)
    )
    first = await design_from_text(
        st0, AgentEnv(llm=FakeLLM({"designer": [_spec(22, 14)]}), audit=False),
        "A three-storey restaurant building.",
    )  # fmt: skip
    assert first.venue is not None
    llm = FakeLLM({"designer": [_spec(22, 14)] * 2})
    projects = _Projects(first.venue)
    st = SimpleNamespace(
        registry=registry, settings=st0.settings, osm=FakeOsm(None), llm=llm,
        usage=SimpleNamespace(add=lambda u: None), projects=projects,
    )  # fmt: skip
    job = redesign.start_redesign(st, "p_1", "Put the stair in the north-east corner.")
    await redesign._tasks["p_1"]
    assert job.status == "done" and job.version == 2
    asked = llm.calls[0][1][-1]["content"]
    assert "Your previous layout" in asked and "north-east corner" in asked
    venue, message = projects.saved[0]
    assert message.startswith("Redesigned:")
    assert venue.extensions["generated"]["redesigns"] == ["Put the stair in the north-east corner."]


def test_a_venue_not_designed_from_words_cannot_be_redesigned(registry: Registry) -> None:
    from api.core.templates import get_template

    st = SimpleNamespace(projects=_Projects(get_template("school_wing")))
    with pytest.raises(redesign.RedesignError, match="not designed from a description"):
        redesign.start_redesign(st, "p_2", "Make it bigger.")
    with pytest.raises(redesign.RedesignError, match="Say what to change"):
        redesign.start_redesign(st, "p_2", " ")


def test_a_plan_no_attack_broke_is_confirmed_only_when_simulated_to_the_end() -> None:
    from api.core.evidence import evaluate

    def run(not_out: int) -> RunResult:
        return RunResult(
            run_id="r", tier=2, status="ok", engine="jupedsim", provider="docker",
            metrics=RunMetrics(evac_time_p95_s=120.0, agents_not_evacuated=not_out),
        )  # fmt: skip

    full = evaluate(run(0), None, confirmation_ran=False, kept=0, had_breaks=False)
    assert full["status"] == "confirmed"
    cut = evaluate(run(12), None, confirmation_ran=False, kept=0, had_breaks=False)
    assert cut["status"] == "unconfirmed"


def test_the_critic_gets_each_floors_exact_counts_with_the_drawing() -> None:
    from api.agents.plan_critic import plan_facts
    from api.core.venue_builder import build_venue
    from api.models.venue_spec import VenueSpec
    from api.tests.test_venue_designer import RESTAURANTS

    facts = plan_facts(build_venue(VenueSpec.model_validate(RESTAURANTS)).venue).splitlines()
    assert len(facts) == 7
    assert facts[0].startswith("- Coffee shop: 30 people; exits: Main entrance 1.5 m")
    assert "exits: none (people leave by the stairs)" in facts[1]
    assert "Kitchen" in facts[1] and "tables:" in facts[1]


async def test_the_critics_points_alone_earn_one_revision(
    registry: Registry, monkeypatch: pytest.MonkeyPatch
) -> None:
    from api.agents import venue_designer
    from api.agents.base import AgentEnv
    from api.agents.plan_critic import Critique
    from api.orchestrator.designing import design_from_text

    async def critic(env: Any, text: str, venue: Any) -> Critique:
        return Critique(matches_description=False, issues=["Add a second lift, as described."])

    monkeypatch.setattr(venue_designer, "critic_on", lambda env: True)
    monkeypatch.setattr(venue_designer, "critique_plan", critic)
    llm = FakeLLM({"designer": [_spec(22, 14)] * 5})
    st = SimpleNamespace(
        registry=registry, settings=Settings(_env_file=None, design_rounds=4), osm=FakeOsm(None)
    )
    out = await design_from_text(st, AgentEnv(llm=llm, audit=False), "A restaurant building.")
    assert out.venue is not None
    assert len(out.venue.extensions["generated"]["design_rounds"]) == 2
    assert len(llm.calls) == 2  # the first design and one revision, not four rounds


def test_a_feature_kind_the_solver_does_not_know_is_kept_as_an_other_feature() -> None:
    from api.models.venue_spec import FeatureSpec

    f = FeatureSpec.model_validate({"kind": "kitchen", "place": "back"})
    assert (f.kind, f.label) == ("other", "kitchen")
    g = FeatureSpec.model_validate({"kind": "lift", "label": "Lift A"})
    assert (g.kind, g.label) == ("other", "Lift A")
