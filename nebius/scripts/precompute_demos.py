"""Build the demo projects with real simulations and the configured model, then save them as
packs in cache/demos/ (installed automatically as sample projects).

`hospital_4f` is a building drawn on the map (the outline below, OpenStreetMap for the
surroundings): four storeys of wards off a corridor, two stair cores, patients in beds,
wheelchair users, older people and staff (S-08). A march demo waits for routes in the simulator
(G2-03).

Usage: make demo-precompute        (takes ~30-40 min; one simulation at a time)
       ... precompute_demos.py t_alley   (one demo)
       ... precompute_demos.py --repack  (rewrite existing packs in the current format)
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import sys
import time
import zipfile
from datetime import date
from pathlib import Path

# Work in a scratch database: SQLite WAL is not safe when the host and the API container
# (Docker Desktop file share) write the same file at once. Packs are what we keep.
os.environ.setdefault(
    "DB_URL", f"sqlite:///{Path(__file__).resolve().parents[1] / 'cache/tmp/precompute.sqlite'}"
)

from api.app.state import build_state
from api.core.building_gen import DEFAULT_GROUPS
from api.core.settings import get_settings
from api.core.templates import get_template
from api.orchestrator import venue_sources
from api.orchestrator.demos import DEMO_DIR
from api.orchestrator.session import SessionManager

DEMOS = {
    "t_alley": {
        "template": "t_alley",
        "event_kind": "festival",
        "name": "Halloween night · T-shaped alley",
        "description": "Itaewon-inspired street: 1,700 people, a 3.2 m alley meets a 6 m street.",
        "location": {
            "lat": 37.5347,
            "lon": 126.9947,
            "timezone": "Asia/Seoul",
            "event_start": "2026-10-31T21:00:00",
        },
        "config": {
            "max_rounds": 2,
            "attacks_per_round": 3,
            "fixes_per_attack": 2,
            "fix_targets": 1,
        },
    },
    "conference_hall": {
        "template": "conference_hall_2f",
        "event_kind": "conference",
        "name": "Tech summit · two-floor hall",
        "description": "1,200 people, two south doors, a mezzanine on one stair.",
        "config": {
            "max_rounds": 2,
            "attacks_per_round": 3,
            "fixes_per_attack": 2,
            "fix_targets": 1,
        },
    },
    "hospital_4f": {
        "map": {
            # a drawn box (about 54 × 33 m) on a city block; not a real hospital
            "outline": [
                [23.7265, 90.392],
                [23.7265, 90.3925],
                [23.7268, 90.3925],
                [23.7268, 90.392],
                [23.7265, 90.392],
            ],
            "levels": 4,
            "use": "hospital",
            "interior": "rooms",
            "people": 600,
        },
        "name": "Riverside General · 4-storey ward block",
        "description": "600 people on four floors of wards, two stair cores; a quarter in beds.",
        "config": {
            "max_rounds": 1,
            "attacks_per_round": 3,
            "fixes_per_attack": 2,
            "fix_targets": 1,
        },
    },
    "festival": {
        "template": "festival_field",
        "event_kind": "concert",
        "name": "Waterfront Spring Festival · Wellington",
        "description": "6,000 people, 20 m stage with a 12 m roof, storm forecast on the day.",
        "location": {
            "lat": -41.2905,
            "lon": 174.7834,
            "timezone": "Pacific/Auckland",
            "event_start": "2026-10-16T09:00:00",
        },
        "stage": {"ballast_kg_per_leg": 3000},
        "snapshot_day": "2026-10-16",
        "config": {
            "max_rounds": 1,
            "attacks_per_round": 3,
            "fixes_per_attack": 2,
            "fix_targets": 1,
        },
    },
}


async def from_map(st, spec: dict) -> object:  # type: ignore[no-untyped-def]
    """A venue drawn on the map, with the usual people mix of its use in every ward."""
    m = spec["map"]
    draft = await venue_sources.from_map(
        st,
        m["outline"],
        mode="indoor",
        name=spec["name"],
        people=m["people"],
        selected_id=None,
        levels=m["levels"],
        use=m["use"],
        interior=m["interior"],
        floor_height_m=3.5,
        event_kind=None,
    )
    venue = draft["venue"] if isinstance(draft, dict) else draft.venue
    data = venue if isinstance(venue, dict) else venue.model_dump()
    usual = [{"kind": k, "share": v} for k, v in DEFAULT_GROUPS.get(m["use"], [])]
    for f in data["floors"]:
        for z in f["zones"]:
            if z["people"] > 0 and not z.get("groups"):
                z["groups"] = usual
    data["event_kind"] = m["use"]
    return data


async def build(st, key: str) -> None:
    spec = DEMOS[key]
    if "map" in spec:
        data = await from_map(st, spec)
        venue = type(get_template("school_wing")).model_validate(data)
    else:
        venue = get_template(spec["template"])
    data = venue.model_dump()
    if "event_kind" in spec:  # the kind of event: the Home tile that opens this sample
        data["event_kind"] = spec["event_kind"]
    if "location" in spec:
        data["location"] = spec["location"]
    if "stage" in spec and data.get("stage"):
        data["stage"].update(spec["stage"])
    if spec.get("snapshot_day"):
        loc = data["location"]
        fc = await st.weather.hourly_gusts(
            loc["lat"], loc["lon"], loc["timezone"], date.fromisoformat(spec["snapshot_day"])
        )
        data.setdefault("extensions", {})["weather_snapshot"] = {
            k: fc[k]
            for k in (
                "times",
                "gust_ms",
                "wind_ms",
                "timezone",
                "source",
                "source_url",
                "fetched_at",
            )
        }
    venue = type(venue).model_validate(data)
    p = st.projects.create(
        spec["name"],
        template_id=spec.get("template"),
        venue=venue,
        description=spec["description"],
        sample=True,
    )
    print(f"[{key}] project {p.id}", flush=True)
    t0 = time.monotonic()
    v = st.projects.venue(p.id)
    await st.runs.run(
        st.runs.build_job(v, tier=3), project_id=p.id, venue_version=1, label="Stress test"
    )
    row = st.sessions.start(p.id, spec["config"])
    await st.sessions.live[row.id].task
    row = st.sessions.get(row.id)
    s = row.summary or {}
    print(
        f"[{key}] session {row.id} {row.status} in {time.monotonic() - t0:.0f} s · scoreboard "
        f"{s.get('scoreboard')} · kept {s.get('accepted_fixes')}",
        flush=True,
    )
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    pack = st.projects.export_zip(p.id, artifacts_from=st.settings.runs_dir)
    out = DEMO_DIR / f"{key}.showtime.zip"
    out.write_bytes(pack)
    print(f"[{key}] wrote {out} ({len(pack) / 1e6:.1f} MB)", flush=True)
    st.projects.delete(p.id)  # the pack is installed as a sample; don't leave a working copy


def repack(st, key: str) -> None:  # type: ignore[no-untyped-def]
    """Rewrite an existing pack in the current (compact) format without re-simulating."""
    path = DEMO_DIR / f"{key}.showtime.zip"
    scratch = st.settings.cache_dir / "tmp" / "repack" / key
    shutil.rmtree(scratch, ignore_errors=True)
    scratch.mkdir(parents=True)
    data = path.read_bytes()
    name = json.loads(zipfile.ZipFile(io.BytesIO(data)).read("project.json"))["name"]
    p = st.projects.import_zip(data, runs_dir=scratch, name=name)
    pack = st.projects.export_zip(p.id, artifacts_from=scratch)
    path.write_bytes(pack)
    st.projects.delete(p.id)
    shutil.rmtree(scratch, ignore_errors=True)
    print(f"[{key}] repacked {len(data) / 1e6:.1f} MB -> {len(pack) / 1e6:.1f} MB", flush=True)


async def main(keys: list[str]) -> None:
    st = build_state(get_settings())
    if keys and keys[0] == "--repack":
        for key in keys[1:] or list(DEMOS):
            repack(st, key)
        return
    st.sessions = SessionManager(st)
    for key in keys or list(DEMOS):
        await build(st, key)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
