"""Geometry validation (section 4.1 step 4): closed rooms, exits on walls, reachability."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from api.core.extensions import geometry as geo
from api.models import Venue

Severity = Literal["error", "warning", "info"]

MIN_EXIT_WIDTH_M = 0.6
MAX_START_DENSITY_PPM2 = 4.0  # zones denser than this cannot be placed with 0.4 m spacing
EXIT_WALL_TOLERANCE_M = 0.6


class Check(BaseModel):
    """One validation finding, located so the UI can highlight it in 3D."""

    code: str
    severity: Severity
    message: str
    hint: str = ""
    target_ids: list[str] = Field(default_factory=list)
    floor_id: str | None = None
    x: float | None = None
    y: float | None = None


class ValidationReport(BaseModel):
    """All findings for a venue."""

    ok: bool
    checks: list[Check]

    @property
    def errors(self) -> list[Check]:
        """Only blocking findings."""
        return [c for c in self.checks if c.severity == "error"]


def _components(geom: Polygon | MultiPolygon) -> list[Polygon]:
    if isinstance(geom, Polygon):
        return [geom] if not geom.is_empty else []
    return [g for g in geom.geoms if g.area > 0.05]


def _component_index(components: list[Polygon], shape: BaseGeometry) -> set[int]:
    return {i for i, comp in enumerate(components) if comp.intersection(shape).area > 1e-3}


def validate_venue(venue: Venue) -> ValidationReport:
    """Run every geometry check. Errors block simulation; warnings are shown."""
    checks: list[Check] = []

    seen: dict[str, int] = {}
    for f in venue.floors:
        for oid in [
            f.floor_id,
            *[o.id for o in f.obstacles],
            *[e.id for e in f.exits],
            *[z.id for z in f.zones],
        ]:
            seen[oid] = seen.get(oid, 0) + 1
    for s in venue.stairs:
        seen[s.id] = seen.get(s.id, 0) + 1
    for oid, n in seen.items():
        if n > 1:
            checks.append(
                Check(
                    code="duplicate_id",
                    severity="error",
                    message=f"The id '{oid}' is used {n} times.",
                    hint="Rename one of the objects.",
                    target_ids=[oid],
                )
            )

    floor_ids = {f.floor_id for f in venue.floors}
    # component index per floor, used for reachability across stairs
    comps: dict[str, list[Polygon]] = {}
    exits_in: dict[tuple[str, int], list[str]] = {}

    for f in venue.floors:
        walk = geo.to_polygon(f.walkable)
        if not Polygon(f.walkable).is_valid:
            checks.append(
                Check(
                    code="walkable_repaired",
                    severity="warning",
                    floor_id=f.floor_id,
                    message=f"The outline of {f.floor_id} crosses itself; "
                    "it was repaired automatically.",
                    hint="Check the corner order of the outline.",
                )
            )
        if walk.area < 1.0:
            checks.append(
                Check(
                    code="walkable_empty",
                    severity="error",
                    floor_id=f.floor_id,
                    message=f"Floor {f.floor_id} has no walkable area.",
                )
            )
            continue
        free = geo.free_space(f)
        parts = _components(free)
        comps[f.floor_id] = parts

        for o in f.obstacles:
            op = geo.to_polygon(o.polygon)
            if op.intersection(walk).area < 1e-3:
                c = op.centroid
                checks.append(
                    Check(
                        code="obstacle_outside",
                        severity="warning",
                        floor_id=f.floor_id,
                        target_ids=[o.id],
                        x=c.x,
                        y=c.y,
                        message=f"'{o.id}' is outside the floor outline.",
                        hint="Move it inside or remove it.",
                    )
                )

        for e in f.exits:
            ep = geo.to_polygon(e.polygon)
            c = ep.centroid
            inside = ep.intersection(free).area / max(ep.area, 1e-9)
            if inside < 0.5:
                checks.append(
                    Check(
                        code="exit_outside",
                        severity="error",
                        floor_id=f.floor_id,
                        target_ids=[e.id],
                        x=c.x,
                        y=c.y,
                        message=f"Exit '{e.id}' is outside the floor or covered by an obstacle.",
                        hint="Move it inside the wall line and run again.",
                    )
                )
                continue
            if ep.distance(walk.exterior) > EXIT_WALL_TOLERANCE_M:
                checks.append(
                    Check(
                        code="exit_not_on_wall",
                        severity="warning",
                        floor_id=f.floor_id,
                        target_ids=[e.id],
                        x=c.x,
                        y=c.y,
                        message=f"Exit '{e.id}' is not on an outer wall.",
                        hint="Exits should sit just inside the outline.",
                    )
                )
            if e.width_m < MIN_EXIT_WIDTH_M:
                checks.append(
                    Check(
                        code="exit_too_narrow",
                        severity="error",
                        floor_id=f.floor_id,
                        target_ids=[e.id],
                        x=c.x,
                        y=c.y,
                        message=f"Exit '{e.id}' is {e.width_m:.2f} m wide; the minimum is "
                        f"{MIN_EXIT_WIDTH_M} m.",
                        hint="Widen the exit.",
                    )
                )
            if e.blocked:
                continue
            for idx in _component_index(parts, ep):
                exits_in.setdefault((f.floor_id, idx), []).append(e.id)

        for z in f.zones:
            zp = geo.to_polygon(z.polygon)
            usable = zp.intersection(free).area
            c = zp.centroid
            if z.people > 0 and usable < 1.0:
                checks.append(
                    Check(
                        code="zone_outside",
                        severity="error",
                        floor_id=f.floor_id,
                        target_ids=[z.id],
                        x=c.x,
                        y=c.y,
                        message=f"Zone '{z.id}' has no walkable space.",
                        hint="Move the zone onto the floor.",
                    )
                )
                continue
            if z.people > 0 and z.people / max(usable, 1e-9) > MAX_START_DENSITY_PPM2:
                checks.append(
                    Check(
                        code="zone_overfull",
                        severity="error",
                        floor_id=f.floor_id,
                        target_ids=[z.id],
                        x=c.x,
                        y=c.y,
                        message=f"Zone '{z.id}' starts at {z.people / usable:.1f} people per m²; "
                        f"at most {MAX_START_DENSITY_PPM2:.1f} can be placed.",
                        hint="Enlarge the zone or lower its headcount.",
                    )
                )
            exit_ids = {e.id for fl in venue.floors for e in fl.exits}
            unknown = [x for x in z.exit_ids if x not in exit_ids]
            if unknown:
                checks.append(
                    Check(
                        code="zone_heading_unknown",
                        severity="error",
                        floor_id=f.floor_id,
                        target_ids=[z.id, *unknown],
                        x=c.x,
                        y=c.y,
                        message=f"People in zone '{z.id}' head for '{unknown[0]}', "
                        "which is not an exit.",
                        hint="Pick one of the exits, or let them use any exit.",
                    )
                )

    stair_links: dict[tuple[str, int], list[tuple[str, int]]] = {}
    for s in venue.stairs:
        if s.from_floor not in floor_ids or s.to_floor not in floor_ids:
            checks.append(
                Check(
                    code="stair_floor_unknown",
                    severity="error",
                    target_ids=[s.id],
                    message=f"Stair '{s.id}' connects a floor that does not exist.",
                )
            )
            continue
        top = _component_index(comps.get(s.from_floor, []), geo.to_polygon(s.top_polygon))
        bottom = _component_index(comps.get(s.to_floor, []), geo.to_polygon(s.bottom_polygon))
        if not top or not bottom:
            which = "top" if not top else "bottom"
            checks.append(
                Check(
                    code="stair_outside",
                    severity="error",
                    target_ids=[s.id],
                    floor_id=s.from_floor if not top else s.to_floor,
                    message=f"The {which} of stair '{s.id}' is not on walkable floor.",
                    hint="Move the stair landing onto the floor.",
                )
            )
            continue
        for t in top:
            stair_links.setdefault((s.from_floor, t), []).extend((s.to_floor, b) for b in bottom)

    def reaches_exit(node: tuple[str, int]) -> bool:
        # breadth-first through any number of stairs (a 40-storey tower is 39 hops); the
        # visited set keeps stairs drawn in a loop from recursing forever
        seen = {node}
        queue = [node]
        while queue:
            here = queue.pop(0)
            if exits_in.get(here):
                return True
            for nxt in stair_links.get(here, []):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        return False

    for f in venue.floors:
        parts = comps.get(f.floor_id, [])
        for z in f.zones:
            if z.people == 0:
                continue
            zp = geo.to_polygon(z.polygon)
            idxs = _component_index(parts, zp)
            if idxs and not any(reaches_exit((f.floor_id, i)) for i in idxs):
                c = zp.centroid
                checks.append(
                    Check(
                        code="zone_no_exit",
                        severity="error",
                        floor_id=f.floor_id,
                        target_ids=[z.id],
                        x=c.x,
                        y=c.y,
                        message=f"People in zone '{z.id}' cannot reach any open exit.",
                        hint="Add an exit or a door in the wall that closes the zone in.",
                    )
                )
            elif len(idxs) > 1:
                checks.append(
                    Check(
                        code="zone_split",
                        severity="info",
                        floor_id=f.floor_id,
                        target_ids=[z.id],
                        message=(
                            f"Zone '{z.id}' spans separate rooms; people are spread across them."
                        ),
                    )
                )

    if venue.total_people() == 0:
        checks.append(
            Check(
                code="no_people",
                severity="warning",
                message="No zone has any people.",
                hint="Set a headcount on a zone.",
            )
        )
    if not any(e for f in venue.floors for e in f.exits if not e.blocked):
        checks.append(
            Check(
                code="no_open_exit",
                severity="error",
                message="The venue has no open exit.",
                hint="Add or unblock an exit.",
            )
        )

    return ValidationReport(ok=not any(c.severity == "error" for c in checks), checks=checks)
