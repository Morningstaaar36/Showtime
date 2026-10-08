"""Wind hazard: Open-Meteo gust forecast vs the stage's wind limit (HazardSource)."""

from __future__ import annotations

import itertools
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field

from api.core.extensions import HazardContext, HazardResult, Registry
from api.models import StageParams

from .stage_check import StageCheckResult, WindAssumptions, check_stage


class Config(BaseModel):
    """Plugin settings (plugin.toml [config])."""

    storm_gust_ms: float = Field(default=20.0, gt=0, le=80)
    event_window_h: float = Field(default=6.0, gt=0, le=72)


@lru_cache(maxsize=256)
def _cached_check(stage_json: str) -> StageCheckResult:
    return check_stage(StageParams.model_validate_json(stage_json), WindAssumptions())


def stage_limit(stage: StageParams) -> StageCheckResult:
    """Cached screening check for a stage."""
    return _cached_check(stage.model_dump_json())


def first_crossing(
    times: list[str], gusts: list[float | None], start: datetime, end: datetime, limit: float
) -> datetime | None:
    """First time (linear interpolation between hourly values) the gust reaches `limit`."""
    pts = [
        (datetime.fromisoformat(t), g) for t, g in zip(times, gusts, strict=False) if g is not None
    ]
    for (t0, g0), (t1, g1) in itertools.pairwise(pts):
        if t1 < start or t0 > end:
            continue
        if g0 >= limit and t0 >= start:
            return t0
        if g0 < limit <= g1:
            frac = (limit - g0) / (g1 - g0)
            hit = t0 + (t1 - t0) * frac
            if start <= hit <= end:
                return hit
            if hit < start <= t1:
                return start
    return None


class WindHazard:
    """Outdoor venues: T_hazard = first forecast time gusts reach the stage's wind limit."""

    id = "hazard_wind"
    label = "Wind on the stage roof"
    modes = ("outdoor",)

    def __init__(self, config: Config) -> None:
        self.config = config

    def stage_check(self, stage: StageParams) -> StageCheckResult:
        """Screening wind limit of a stage (cached)."""
        return stage_limit(stage)

    async def evaluate(self, ctx: HazardContext) -> HazardResult | None:
        venue = ctx.venue
        if venue.mode != "outdoor" or venue.location is None:
            return None
        threshold_src = "storm threshold"
        details: dict[str, Any] = {}
        limit = float(ctx.manual.get("storm_gust_ms", self.config.storm_gust_ms))
        if venue.stage is not None and "storm_gust_ms" not in ctx.manual:
            chk = stage_limit(venue.stage)
            limit = chk.v_limit_ms
            threshold_src = f"stage wind limit ({chk.governing})"
            details["stage_check"] = chk.model_dump()
        details["limit_ms"] = limit
        details["threshold_source"] = threshold_src
        start_iso = venue.location.event_start
        start = (
            datetime.fromisoformat(start_iso)
            if start_iso
            else datetime.now().replace(minute=0, second=0, microsecond=0)
        )
        end = start + timedelta(hours=self.config.event_window_h)
        manual_gust = ctx.manual.get("gust_ms")
        if manual_gust is not None:
            details["manual_gust_ms"] = manual_gust
            if manual_gust >= limit:
                return HazardResult(
                    source=self.id,
                    t_hazard_s=0.0,
                    t_hazard_iso=start.isoformat(),
                    explanation=f"Entered gust {manual_gust:.1f} m/s already reaches the "
                    f"{threshold_src} of {limit:.1f} m/s.",
                    details=details,
                )
            return HazardResult(
                source=self.id,
                explanation=(
                    f"Entered gust {manual_gust:.1f} m/s stays below the {threshold_src} "
                    f"of {limit:.1f} m/s."
                ),
                details=details,
            )
        snapshot = (venue.extensions or {}).get("weather_snapshot")
        if snapshot:
            # a forecast saved with the plan (demos, offline use): labelled with its fetch time
            fc = dict(snapshot)
            fc["source"] = (
                f"{fc.get('source', 'Open-Meteo forecast')} (snapshot {fc.get('fetched_at', '')[:16]})"
            )
        elif ctx.get_forecast is None:
            return HazardResult(
                source=self.id, explanation="No weather provider configured.", details=details
            )
        else:
            fc = await ctx.get_forecast(
                venue.location.lat,
                venue.location.lon,
                start.date().isoformat(),
                venue.location.timezone,
            )
        details["forecast"] = {
            k: fc.get(k)
            for k in ("times", "gust_ms", "source", "source_url", "fetched_at", "cached")
        }
        hit = first_crossing(fc.get("times", []), fc.get("gust_ms", []), start, end, limit)
        window = f"{start:%H:%M}–{end:%H:%M}"
        if hit is None:
            peak = max((g for g in fc.get("gust_ms", []) if g is not None), default=0.0)
            return HazardResult(
                source=self.id,
                explanation=(
                    f"No hazard in forecast window ({window}): gusts peak at {peak:.1f} m/s, "
                    f"below the {threshold_src} of {limit:.1f} m/s."
                ),
                details=details,
            )
        t_s = max((hit - start).total_seconds(), 0.0)
        return HazardResult(
            source=self.id,
            t_hazard_s=round(t_s, 0),
            t_hazard_iso=hit.isoformat(),
            explanation=(
                f"Forecast gusts reach {limit:.1f} m/s (the {threshold_src}) at "
                f"{hit:%H:%M} ({fc.get('source', 'forecast')}, hourly, interpolated)."
            ),
            details=details,
        )


def showtime_register(registry: Registry, config: Config) -> None:
    """Register the wind hazard source."""
    registry.add("HazardSource", WindHazard.id, WindHazard(config))
