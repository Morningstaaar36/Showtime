"""What each kind of event or building means for the crowd (GET /api/v1/event-kinds).

The labels and descriptions are plain copy; the usual people mix and interior come from the
building generator's defaults. Pre-movement stays None (the run default) until a kind has a
cited value: no behaviour number is shown without a source (docs/ASSUMPTIONS.md).
"""

from __future__ import annotations

from typing import Any, get_args

from api.core.building_gen import DEFAULT_GROUPS, default_interior
from api.models.venue import EventKind

_COPY: dict[str, tuple[str, str]] = {
    "concert": ("Concert", "A standing or seated crowd facing a stage."),
    "festival": ("Festival", "Several stages and stalls; people move around all day."),
    "conference": ("Conference", "Seated audiences in halls and rooms."),
    "wedding": ("Wedding", "Guests of all ages, including older people and children."),
    "rally": ("Rally", "A dense standing crowd in an open space."),
    "march": ("March", "A crowd walking a route in order."),
    "sports": ("Sports", "Seated stands that empty at the same moment."),
    "religious": ("Religious gathering", "Large crowds at fixed times, often with older people."),
    "hospital": ("Hospital", "Patients, some in beds or wheelchairs, with staff who help."),
    "school": ("School", "Children in classrooms with teachers."),
    "office": ("Office", "Adults at desks and in meeting rooms."),
    "mall": ("Shopping mall", "Shoppers spread over shops and corridors."),
    "transit": ("Station", "Passengers with luggage on platforms and concourses."),
    "residential": ("Homes", "Residents of all ages, some asleep at night."),
    "other": ("Other", "General adults."),
}


def event_kinds() -> list[dict[str, Any]]:
    """Every event kind with its copy, usual people mix and usual interior."""
    out = []
    for kind in get_args(EventKind):
        label, description = _COPY[kind]
        out.append(
            {
                "id": kind,
                "label": label,
                "description": description,
                "default_pre_movement_s": None,
                "default_groups": [
                    {"kind": k, "share": s} for k, s in DEFAULT_GROUPS.get(kind, [])
                ],
                "interior": default_interior(kind),
            }
        )
    return out
