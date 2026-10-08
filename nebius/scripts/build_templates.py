"""Generate the template venues in api/data/templates/ (section 4.3).

Run: `uv run --project api python scripts/build_templates.py`
Coordinates: x grows east, y grows north, metres.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "api" / "data" / "templates"
WALL = 0.2  # interior wall thickness (m)


def rect(x0: float, y0: float, x1: float, y1: float) -> list[list[float]]:
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def exit_rect(wall: str, edge: float, a: float, b: float, depth: float = 0.4) -> list[list[float]]:
    """Exit area just inside a wall line `edge`, spanning a..b along the wall."""
    inset = 0.02
    if wall == "south":
        return rect(a, edge + inset, b, edge + inset + depth)
    if wall == "north":
        return rect(a, edge - inset - depth, b, edge - inset)
    if wall == "west":
        return rect(edge + inset, a, edge + inset + depth, b)
    return rect(edge - inset - depth, a, edge - inset, b)


def conference_hall() -> dict:
    return {
        "venue_id": "conference_hall_2f",
        "name": "Conference hall, 2 floors",
        "description": (
            "40 × 25 m hall, stage on the north wall, two 2.5 m doors on the south wall, "
            "a mezzanine reached by one stairwell in the north-east corner. 1,200 people."
        ),
        "mode": "indoor",
        "floors": [
            {
                "floor_id": "F0",
                "name": "Ground floor",
                "elevation_m": 0,
                "walkable": rect(0, 0, 40, 25),
                "obstacles": [
                    {
                        "id": "stage",
                        "kind": "stage",
                        "polygon": rect(12, 20, 28, 25),
                        "height_m": 1.0,
                        "label": "Stage",
                    },
                    {
                        "id": "stair_ne_structure",
                        "kind": "other",
                        "polygon": rect(36, 14, 39.5, 22),
                        "height_m": 4.5,
                        "label": "Stair structure",
                    },
                    {
                        "id": "foh_desk",
                        "kind": "booth",
                        "polygon": rect(18.5, 4.5, 21.5, 6.0),
                        "height_m": 1.2,
                        "label": "Sound desk",
                    },
                ],
                "exits": [
                    {
                        "id": "door_s1",
                        "polygon": exit_rect("south", 0, 7.75, 10.25),
                        "width_m": 2.5,
                        "label": "South door 1",
                    },
                    {
                        "id": "door_s2",
                        "polygon": exit_rect("south", 0, 29.75, 32.25),
                        "width_m": 2.5,
                        "label": "South door 2",
                    },
                ],
                "zones": [
                    {
                        "id": "audience",
                        "polygon": rect(4, 7, 34, 18),
                        "people": 900,
                        "label": "Audience",
                    },
                ],
            },
            {
                "floor_id": "F1",
                "name": "Mezzanine",
                "elevation_m": 4.5,
                "walkable": rect(0, 15, 40, 25),
                "obstacles": [],
                "exits": [],
                "zones": [
                    {
                        "id": "mezzanine",
                        "polygon": rect(2, 17, 30, 24),
                        "people": 300,
                        "label": "Mezzanine seating",
                    },
                ],
            },
        ],
        "stairs": [
            {
                "id": "stair_ne",
                "from_floor": "F1",
                "to_floor": "F0",
                "top_polygon": rect(36, 20, 39, 24),
                "bottom_polygon": rect(36, 10, 39, 14),
                "width_m": 2.0,
                "length_m": 9.0,
            }
        ],
        "stage": None,
        "location": {
            "lat": 23.7265,
            "lon": 90.3925,
            "timezone": "Asia/Dhaka",
            "event_start": "2026-11-20T18:00:00",
        },
        "rules_profile": "default",
    }


def school_wing() -> dict:
    # Corridor y 8..11 runs the full length; stairwell exits at both corridor ends.
    x0, x1 = 4.0, 40.0
    room_w = (x1 - x0) / 4
    walkable = [
        [4, 0],
        [40, 0],
        [40, 8],
        [44, 8],
        [44, 11],
        [40, 11],
        [40, 19],
        [4, 19],
        [4, 11],
        [0, 11],
        [0, 8],
        [4, 8],
    ]
    obstacles: list[dict] = []
    zones: list[dict] = []
    for side, (y_wall, y_room0, y_room1) in {"s": (8.0, 0.0, 8.0), "n": (11.0, 11.0, 19.0)}.items():
        # corridor wall with one 1.2 m door per classroom, near the room's west side
        doors = [(x0 + i * room_w + 1.0, x0 + i * room_w + 2.2) for i in range(4)]
        cursor = x0 - 0.1
        for k, (da, db) in enumerate(doors):
            if da > cursor:
                obstacles.append(
                    {
                        "id": f"wall_{side}{k}",
                        "kind": "wall",
                        "polygon": rect(cursor, y_wall - WALL / 2, da, y_wall + WALL / 2),
                        "height_m": 3.0,
                    }
                )
            cursor = db
        obstacles.append(
            {
                "id": f"wall_{side}4",
                "kind": "wall",
                "polygon": rect(cursor, y_wall - WALL / 2, x1 + 0.1, y_wall + WALL / 2),
                "height_m": 3.0,
            }
        )
        for i in range(1, 4):
            xd = x0 + i * room_w
            obstacles.append(
                {
                    "id": f"div_{side}{i}",
                    "kind": "wall",
                    "polygon": rect(xd - WALL / 2, y_room0 - 0.1, xd + WALL / 2, y_room1 + 0.1),
                    "height_m": 3.0,
                }
            )
        for i in range(4):
            rx = x0 + i * room_w
            num = (1 if side == "s" else 5) + i
            zones.append(
                {
                    "id": f"room_{num}",
                    "label": f"Classroom {num}",
                    "polygon": rect(rx + 0.6, y_room0 + 0.6, rx + room_w - 0.6, y_room1 - 0.6),
                    "people": 50,
                }
            )
    return {
        "venue_id": "school_wing",
        "name": "School wing",
        "description": (
            "One floor: a 3 m corridor with 8 classrooms of 50 pupils, "
            "stairwell exits (1.5 m) at both ends of the corridor. 400 people."
        ),
        "mode": "indoor",
        "floors": [
            {
                "floor_id": "F0",
                "name": "First floor",
                "elevation_m": 0,
                "walkable": walkable,
                "obstacles": obstacles,
                "exits": [
                    {
                        "id": "stair_w",
                        "polygon": exit_rect("west", 0, 8.75, 10.25),
                        "width_m": 1.5,
                        "label": "West stairwell",
                    },
                    {
                        "id": "stair_e",
                        "polygon": exit_rect("east", 44, 8.75, 10.25),
                        "width_m": 1.5,
                        "label": "East stairwell",
                    },
                ],
                "zones": zones,
            }
        ],
        "stairs": [],
        "stage": None,
        "location": {
            "lat": 23.7265,
            "lon": 90.3925,
            "timezone": "Asia/Dhaka",
            "event_start": "2026-11-20T10:00:00",
        },
        "rules_profile": "default",
    }


def festival_field() -> dict:
    return {
        "venue_id": "festival_field",
        "name": "Festival field",
        "description": (
            "Open-air 80 × 50 m field, 20 m stage with a 12 m roof on the north side, "
            "two 6 m gates in the south fence, bars on both sides. 6,000 people."
        ),
        "mode": "outdoor",
        "floors": [
            {
                "floor_id": "F0",
                "name": "Field",
                "elevation_m": 0,
                "walkable": rect(0, 0, 80, 50),
                "obstacles": [
                    {
                        "id": "stage",
                        "kind": "stage",
                        "polygon": rect(30, 42, 50, 50),
                        "height_m": 12.0,
                        "label": "Main stage",
                    },
                    {
                        "id": "front_barrier",
                        "kind": "barrier",
                        "polygon": rect(27, 39.85, 53, 40.15),
                        "height_m": 1.1,
                        "line": [[27, 40], [53, 40]],
                        "label": "Front-of-stage barrier",
                    },
                    {
                        "id": "foh_tent",
                        "kind": "booth",
                        "polygon": rect(37, 18, 43, 22),
                        "height_m": 3.0,
                        "label": "Front-of-house tent",
                    },
                    {
                        "id": "bar_w",
                        "kind": "bar",
                        "polygon": rect(1, 20, 6, 32),
                        "height_m": 3.0,
                        "label": "West bar",
                    },
                    {
                        "id": "bar_e",
                        "kind": "bar",
                        "polygon": rect(74, 20, 79, 32),
                        "height_m": 3.0,
                        "label": "East bar",
                    },
                ],
                "exits": [
                    {
                        "id": "gate_sw",
                        "polygon": exit_rect("south", 0, 14, 20),
                        "width_m": 6.0,
                        "label": "South-west gate",
                    },
                    {
                        "id": "gate_se",
                        "polygon": exit_rect("south", 0, 60, 66),
                        "width_m": 6.0,
                        "label": "South-east gate",
                    },
                ],
                "zones": [
                    {
                        "id": "front",
                        "polygon": rect(12, 28, 68, 39),
                        "people": 1700,
                        "label": "Front of stage",
                    },
                    {
                        "id": "middle",
                        "polygon": rect(8, 14, 72, 28),
                        "people": 2600,
                        "label": "Middle field",
                    },
                    {
                        "id": "back",
                        "polygon": rect(8, 3, 72, 14),
                        "people": 1700,
                        "label": "Back field",
                    },
                ],
            }
        ],
        "stairs": [],
        "stage": {
            "width_m": 20,
            "depth_m": 8,
            "roof_height_m": 12,
            "roof_area_m2": 160,
            "legs": 6,
            "ballast_kg_per_leg": 2000,
            "friction_coeff": 0.5,
            "force_coeff": 1.3,
            "banner_area_m2": 60,
        },
        "location": {
            "lat": 23.7806,
            "lon": 90.4193,
            "timezone": "Asia/Dhaka",
            "event_start": "2026-11-20T18:00:00",
        },
        "rules_profile": "default",
    }


def t_alley() -> dict:
    # Itaewon-inspired: 3.2 m wide x 45 m long sloped alley meeting a 6 m street at a T.
    # Dimensions: Wikipedia "Seoul Halloween crowd crush" (alley about 45 m long, 3.2 m wide).
    aw = 3.2
    cx = 60.0
    ax0 = cx - aw / 2
    ax1 = cx + aw / 2
    walkable = [[ax0, 0], [ax1, 0], [ax1, 45], [120, 45], [120, 51], [0, 51], [0, 45], [ax0, 45]]
    return {
        "venue_id": "t_alley",
        "name": "T-shaped alley",
        "description": (
            "Open-air street: a 3.2 m wide, 45 m long sloped alley meets a 6 m wide street "
            "at a T, inspired by the published dimensions of the Itaewon alley (Seoul, 2022). "
            "1,700 people."
        ),
        "mode": "outdoor",
        "floors": [
            {
                "floor_id": "F0",
                "name": "Street level",
                "elevation_m": 0,
                "walkable": walkable,
                "obstacles": [],
                "exits": [
                    {
                        "id": "alley_s",
                        "polygon": exit_rect("south", 0, ax0 + 0.05, ax1 - 0.05),
                        "width_m": round(aw - 0.1, 2),
                        "label": "Alley to main road",
                    },
                    {
                        "id": "street_w",
                        "polygon": exit_rect("west", 0, 45.2, 50.8),
                        "width_m": 5.6,
                        "label": "Street west end",
                    },
                    {
                        "id": "street_e",
                        "polygon": exit_rect("east", 120, 45.2, 50.8),
                        "width_m": 5.6,
                        "label": "Street east end",
                    },
                ],
                "zones": [
                    {
                        "id": "street",
                        "polygon": rect(4, 45.5, 116, 50.5),
                        "people": 1400,
                        "label": "Top street",
                    },
                    {
                        "id": "alley",
                        "polygon": [
                            [ax0 + 0.2, 8],
                            [ax1 - 0.2, 8],
                            [ax1 - 0.2, 44.5],
                            [ax0 + 0.2, 44.5],
                        ],
                        "people": 300,
                        "label": "Alley",
                    },
                ],
            }
        ],
        "stairs": [],
        "stage": None,
        "location": {
            "lat": 37.5347,
            "lon": 126.9947,
            "timezone": "Asia/Seoul",
            "event_start": "2026-10-31T21:00:00",
        },
        "rules_profile": "default",
        "extensions": {
            "sources": [
                {
                    "label": "Seoul Halloween crowd crush (Wikipedia): alley about 45 m long and "
                    "3.2 m wide",
                    "url": "https://en.wikipedia.org/wiki/Seoul_Halloween_crowd_crush",
                }
            ],
            "slope_note": "The real alley slopes downhill to the south (about 10%); "
            "the simulation treats it as flat.",
        },
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for fn in (conference_hall, school_wing, festival_field, t_alley):
        data = fn()
        (OUT / f"{data['venue_id']}.json").write_text(json.dumps(data, indent=2) + "\n")
        print("wrote", data["venue_id"])


if __name__ == "__main__":
    main()
