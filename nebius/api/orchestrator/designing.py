"""A venue designed from words, with everything the server knows wired in.

The designer agent (api/agents/venue_designer.py) takes its helpers as arguments; this module
gives it the real ones: the plan checker and instant estimate (api/core/design_review.py), the
real building on the map (api/orchestrator/site.py) and the number of design rounds
(DESIGN_ROUNDS). Descriptions, real cases and Autopilot all design through here, so they
behave the same way.
"""

from __future__ import annotations

from typing import Any

from api.agents.base import AgentEnv
from api.agents.venue_designer import DesignOutcome, Progress, design_venue
from api.core.design_review import DesignReview, review_design
from api.models import Location, Venue
from api.models.venue_spec import VenueSpec
from api.orchestrator.site import find_site


async def design_from_text(
    st: Any,
    env: AgentEnv,
    text: str,
    people: int | None = None,
    *,
    location: Location | None = None,
    progress: Progress | None = None,
    start: VenueSpec | None = None,
    request: str = "",
) -> DesignOutcome:
    """Design a venue in rounds; `location` (a real case's) pins the site to look up.

    `start` and `request` redesign an earlier layout with the organizer's own words.
    """

    def review(spec: VenueSpec, venue: Venue) -> DesignReview:
        return review_design(text, spec, venue, st.registry, st.settings)

    async def site_of(spec: VenueSpec) -> dict[str, Any] | None:
        # only a building stands on one plot of the map; an open-air site is drawn as described
        if spec.building is None and spec.mode != "indoor":
            return None
        site = await find_site(
            st,
            lat=location.lat if location else None,
            lon=location.lon if location else None,
            place=None if location else spec.location,
            described_m2=spec.width_m * spec.depth_m,
        )
        if site is None:
            return None
        return {**site.as_dict(), "brief": site.brief(), "neighbours": site.neighbours}

    return await design_venue(
        env,
        text,
        people,
        review=review,
        site_of=site_of,
        progress=progress,
        rounds=int(st.settings.design_rounds),
        start=start,
        request=request,
    )
