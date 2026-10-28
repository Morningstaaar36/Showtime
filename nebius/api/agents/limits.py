"""What makes an AI-proposed scenario plausible enough to simulate: events start early enough to
matter, and a surge or counterflow is a share of the crowd, not a second crowd. Shared by the red
team and the what-if designer; the numbers are settings."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EventLimits:
    max_start_s: float
    surge_share: float
    counterflow_share: float
    min_people: int  # a small crowd may still see a group this big

    @classmethod
    def of(cls, s: Any) -> EventLimits:
        return cls(
            s.attack_max_start_s,
            s.surge_max_share,
            s.counterflow_max_share,
            s.attack_min_people,
        )


def event_problems(events: Iterable[Any], total: int, lim: EventLimits) -> list[str]:
    """Why proposed events are implausible for a crowd of `total` (empty when they are fine)."""
    out: list[str] = []
    for e in events:
        if e.type == "surge" and e.extra_people > max(lim.min_people, total * lim.surge_share):
            out.append(
                f"a surge of {e.extra_people} is more than {lim.surge_share:.0%} of the crowd"
            )
        if e.type == "counterflow" and e.people > max(
            lim.min_people, total * lim.counterflow_share
        ):
            out.append(
                f"a counterflow of {e.people} is more than {lim.counterflow_share:.0%} of the crowd"
            )
        if e.at_s > lim.max_start_s:
            out.append(f"events must start within the first {lim.max_start_s:g} s")
    return out
