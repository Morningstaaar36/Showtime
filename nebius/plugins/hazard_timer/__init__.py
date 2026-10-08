"""Scenario clock: T_hazard from the scenario (exit lost, power cut) or a user-set time."""

from __future__ import annotations

from pydantic import BaseModel

from api.core.extensions import HazardContext, HazardResult, Registry

HAZARD_EVENTS = {"block_exit": "exit {exit_id} becomes unusable"}


class Config(BaseModel):
    """No settings yet."""


class TimerHazard:
    """T_hazard = first scenario event that removes a route, or a time set by the user."""

    id = "hazard_timer"
    label = "Scenario clock"
    modes = ("indoor", "outdoor")

    async def evaluate(self, ctx: HazardContext) -> HazardResult | None:
        manual = ctx.manual.get("hazard_time_s")
        if manual is not None:
            return HazardResult(
                source=self.id,
                t_hazard_s=float(manual),
                explanation=f"Hazard time set by you: {float(manual):.0f} s after the alarm.",
                details={"kind": "manual"},
                label="user input",
            )
        if ctx.attack is None:
            return None
        hits = []
        for ev in ctx.attack.events:
            if ev.type in HAZARD_EVENTS:
                data = ev.model_dump()
                try:
                    text = HAZARD_EVENTS[ev.type].format(**data)
                except KeyError:
                    text = ev.type
                hits.append((float(ev.at_s), text))
        if not hits:
            return None
        t, text = min(hits)
        return HazardResult(
            source=self.id,
            t_hazard_s=t,
            explanation=f"In scenario “{ctx.attack.title}”, {text} at {t:.0f} s.",
            details={"kind": "scenario", "attack_id": ctx.attack.attack_id},
            label="scenario",
        )


def showtime_register(registry: Registry, config: Config) -> None:
    """Register the scenario clock."""
    registry.add("HazardSource", TimerHazard.id, TimerHazard())
