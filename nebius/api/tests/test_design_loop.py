"""The design rounds with the server's helpers wired in, and "Let the AI fix it".

Design: the real building on the map sends a layout of the wrong size back to the designer, a
building the map does not have is said in the notes, and every round is recorded on the venue.
Improve: a test's proven fixes become a version and the next test runs on it, until no attack
breaks the plan or a test keeps no fix.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from api.adapters.llm import FakeLLM
from api.agents.base import AgentEnv
from api.core.extensions import Registry
from api.core.osm_venue import Projector
from api.core.settings import Settings
from api.models import Location
from api.orchestrator import improve
from api.orchestrator.designing import design_from_text

LAT, LON = 23.7409, 90.4078


def _spec(width: float, depth: float) -> dict[str, Any]:
    return {
        "name": "Restaurant building",
        "width_m": width,
        "depth_m": depth,
        "exits": [{"wall": "south", "width_m": 1.5, "position": 0.5, "label": "Main entrance"}],
        "building": {
            "storeys": 3,
            "use": "mall",
            "interior": "dining",
            "people_per_floor": 30,
            "stairs": [{"place": "north", "width_m": 1.2}],
        },
    }


class FakeOsm:
    """One building of `w` × `d` metres around the point, or none."""

    def __init__(self, w: float | None, d: float | None = None) -> None:
        self.w, self.d = w, d

    async def search(self, q: str, limit: int = 6) -> list[dict[str, Any]]:
        return [{"lat": LAT, "lon": LON, "display_name": "New Bailey Road, Dhaka"}]

    async def at_point(self, lat: float, lon: float) -> dict[str, Any]:
        if self.w is None or self.d is None:
            return {"selection": None}
        pr = Projector(lat, lon)
        hw, hd = self.w / 2, self.d / 2
        ring = [pr.latlon(x, y) for x, y in [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]]
        return {
            "selection": {
                "kind": "building",
                "id": 42,
                "coords": [list(c) for c in ring],
                "tags": {"building": "commercial", "building:levels": "3"},
            }
        }

    async def features(self, *box: float) -> dict[str, Any]:
        return {"features": []}


def _st(registry: Registry, osm: FakeOsm, rounds: int = 2) -> Any:
    return SimpleNamespace(
        registry=registry, settings=Settings(_env_file=None, design_rounds=rounds), osm=osm
    )


async def test_a_layout_off_the_real_buildings_size_goes_back_with_the_size(
    registry: Registry,
) -> None:
    llm = FakeLLM({"designer": [_spec(30, 20), _spec(22, 14)]})
    out = await design_from_text(
        _st(registry, FakeOsm(22, 14)),
        AgentEnv(llm=llm, audit=False),
        "A three-storey restaurant building on New Bailey Road, Dhaka.",
        location=Location(lat=LAT, lon=LON),
    )
    assert len(llm.calls) == 2
    revision = llm.calls[1][1][-1]["content"]
    assert "OpenStreetMap way 42" in revision and "22 m east-west" in revision
    assert out.venue is not None and out.spec is not None
    assert (out.spec.width_m, out.spec.depth_m) == (22, 14)
    gen = out.venue.extensions["generated"]
    assert [r["round"] for r in gen["design_rounds"]] == [1, 2]
    assert [r["kept"] for r in gen["design_rounds"]] == [False, True]
    assert gen["site"]["source"] == "OpenStreetMap way 42"


async def test_no_building_on_the_map_is_said_and_the_described_size_kept(
    registry: Registry,
) -> None:
    llm = FakeLLM({"designer": [_spec(22, 14)] * 3})
    stages: list[str] = []
    out = await design_from_text(
        _st(registry, FakeOsm(None)),
        AgentEnv(llm=llm, audit=False),
        "A three-storey restaurant building in Dhaka.",
        location=Location(lat=LAT, lon=LON),
        progress=lambda e: stages.append(e["stage"]),
    )
    assert out.venue is not None and out.spec is not None
    assert (out.spec.width_m, out.spec.depth_m) == (22, 14)
    assert any("no building outline" in n for n in out.notes)
    assert stages[0] == "designing" and stages[-1] == "done"


async def test_an_organizers_change_revises_the_earlier_layout(registry: Registry) -> None:
    llm = FakeLLM({"designer": [_spec(22, 14)] * 3})
    from api.models.venue_spec import VenueSpec

    await design_from_text(
        _st(registry, FakeOsm(None), rounds=1),
        AgentEnv(llm=llm, audit=False),
        "A three-storey restaurant building.",
        start=VenueSpec.model_validate(_spec(22, 14)),
        request="Put the stair in the north-east corner.",
    )
    first = llm.calls[0][1][-1]["content"]
    assert "Your previous layout" in first and "north-east corner" in first


# --- Let the AI fix it -------------------------------------------------------------------


class FakeSessions:
    """Sessions that finish at once with scripted results; apply makes a new version."""

    def __init__(self, results: list[dict[str, Any]]) -> None:
        self.results = results
        self.rows: dict[str, Any] = {}
        self.version = 1
        self.applied: list[str] = []
        self._new(1)

    def _new(self, version: int) -> Any:
        i = len(self.rows)
        r = self.results[i]
        row = SimpleNamespace(
            id=f"s_{i}",
            project_id="p_1",
            venue_version=version,
            status="finished",
            config={"max_rounds": 1},
            summary={
                "scoreboard": [{"round": 1, "breaks": r["breaks"], "attacks": 3}],
                "accepted_fixes": r["kept"],
                "fixes": [{"fix_id": f, "title": f"Fix {f}"} for f in r["kept"]],
                "before": {"evac_time_p95_s": 300.0},
                "after": {"evac_time_p95_s": 200.0},
            },
        )
        self.rows[row.id] = row
        return row

    def get(self, sid: str) -> Any:
        return self.rows.get(sid)

    def apply_final(self, sid: str) -> Any:
        self.applied.append(sid)
        self.version += 1
        return SimpleNamespace(version=self.version)

    def start(self, project_id: str, config: dict[str, Any]) -> Any:
        # the same test again, now confirming its kept fixes with full simulations
        assert config == {"max_rounds": 1, "confirm_tier3": True}
        return self._new(self.version)


def _improve_st(results: list[dict[str, Any]]) -> Any:
    return SimpleNamespace(
        sessions=FakeSessions(results), settings=Settings(_env_file=None, improve_rounds=3)
    )


async def _run(st: Any) -> improve.ImproveLoop:
    loop = improve.start_improve(st, "s_0")
    assert loop.task is not None
    await asyncio.wait_for(loop.task, 5)
    return loop


async def test_fixes_are_applied_and_tested_again_until_nothing_breaks() -> None:
    st = _improve_st(
        [{"breaks": 3, "kept": ["F1"]}, {"breaks": 1, "kept": ["F2"]}, {"breaks": 0, "kept": []}]
    )
    loop = await _run(st)
    assert loop.status == "holds"
    assert [i.breaks for i in loop.iterations] == [3, 1, 0]
    assert [i.applied_version for i in loop.iterations] == [2, 3, None]
    assert [i.version for i in loop.iterations] == [1, 2, 3]
    assert st.sessions.applied == ["s_0", "s_1"]
    assert improve.loop_for("s_2") is loop  # every test of the loop finds it
    assert loop.as_dict()["current_session_id"] == "s_2"


async def test_the_loop_stops_when_no_fix_held() -> None:
    loop = await _run(_improve_st([{"breaks": 2, "kept": []}]))
    assert loop.status == "no_fix" and "2 of 3 attacks" in loop.detail
    assert loop.iterations[0].applied_version is None


async def test_the_loop_stops_after_its_rounds_with_the_last_fixes_saved() -> None:
    st = _improve_st([{"breaks": 2, "kept": ["F1"]}] * 3)
    loop = await _run(st)
    assert loop.status == "rounds_used" and len(loop.iterations) == 3
    assert loop.iterations[-1].applied_version == 4


def test_the_critic_may_only_hold_the_plan_to_what_the_description_says() -> None:
    from api.agents.plan_critic import Issue, grounded

    text = "There is only one staircase, about 1.2 m wide. The only way out is the street door."
    kept, dropped = grounded(
        text,
        [
            Issue(issue="Show one staircase, not two.", quote="There is ONLY one staircase,"),
            Issue(issue="Add a street exit on floor 6.", quote="an exit on every floor"),
            Issue(issue="Show two lifts.", quote=""),
        ],
    )
    assert kept == ["Show one staircase, not two."]
    assert dropped == ["Add a street exit on floor 6.", "Show two lifts."]


def test_a_new_door_with_its_policy_applies_to_a_building_with_no_organizer_plan(
    registry: Registry,
) -> None:
    from api.agents.blue_team import check_fix
    from api.core.venue_builder import build_venue
    from api.models.venue_spec import VenueSpec

    venue = build_venue(VenueSpec.model_validate(_spec(22, 14))).venue
    problems = check_fix(
        registry,
        venue,
        [
            {
                "op": "add_exit",
                "floor_id": "F0",
                "id": "door_w1",
                "wall": "east",
                "center": 7,
                "width_m": 1.5,
            }
        ],
        [],
        new_objects={"door_w1": {"origin": "proposed"}},
    )
    assert problems == []


def test_the_blue_team_is_told_how_the_upper_floors_get_down() -> None:
    from api.agents.blue_team import _ways_down
    from api.core.venue_builder import build_venue
    from api.models.venue_spec import VenueSpec

    venue = build_venue(VenueSpec.model_validate(_spec(22, 14))).venue
    line = _ways_down(venue)
    assert "1 stairwell(s)" in line and "1.2 m wide" in line and "for 60 people" in line


def test_lifts_the_layout_places_are_not_doubled_by_the_fit_out() -> None:
    from api.core.venue_builder import build_venue
    from api.models.venue_spec import VenueSpec

    spec = _spec(22, 14)
    spec["features"] = [
        {
            "kind": "other",
            "label": "Lift 1",
            "place": "east",
            "width_m": 2,
            "depth_m": 2,
            "level": 0,
        }
    ]
    venue = build_venue(VenueSpec.model_validate(spec)).venue
    ground = [o.label for o in venue.floors[0].obstacles if "lift" in (o.label or "").lower()]
    upper = [o.label for o in venue.floors[1].obstacles if "lift" in (o.label or "").lower()]
    assert ground == ["Lift 1"]
    assert upper == ["Lift (not used in a fire)"]
