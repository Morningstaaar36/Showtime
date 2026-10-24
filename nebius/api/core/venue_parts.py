"""Solver parts for one-level sites: passages (a tunnel, ramp, alley or access road joined to a
wall of the main floor, with an optional area at its far end) and dividers (fences that split
the main floor into pens).

Every passage has a local frame: `s` runs from where it joins the main floor (0) away from it,
`t` runs across it, positive to the left of someone walking in. The model only gives sizes and
positions along walls; the coordinates come from here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from api.core.extensions import geometry as geo
from api.models import Exit, Obstacle
from api.models.venue_spec import PassageExitSpec, PassageSpec, VenueSpec, Wall

EXIT_DEPTH_M = 0.4
INSET_M = 0.02
DIVIDER_M = 0.2

# walking out of the main floor through each wall: (direction out, direction to the left)
_FRAME: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {
    "north": ((0.0, 1.0), (-1.0, 0.0)),
    "south": ((0.0, -1.0), (1.0, 0.0)),
    "east": ((1.0, 0.0), (0.0, 1.0)),
    "west": ((-1.0, 0.0), (0.0, -1.0)),
}


@dataclass
class PassagePart:
    """One passage, solved: its outline, the area at its end, and what it holds."""

    spec: PassageSpec
    origin: tuple[float, float]
    out: tuple[float, float]
    left: tuple[float, float]
    strip: Polygon
    area: Polygon | None
    opening: Polygon  # just inside the main floor where it joins (kept clear of exits)
    exits: list[Exit] = field(default_factory=list)
    obstacles: list[Obstacle] = field(default_factory=list)

    def at(self, s: float, t: float) -> tuple[float, float]:
        ox, oy = self.origin
        return (
            round(ox + s * self.out[0] + t * self.left[0], 4),
            round(oy + s * self.out[1] + t * self.left[1], 4),
        )

    def box(self, s0: float, s1: float, t0: float, t1: float) -> Polygon:
        """Axis-aligned rectangle between two (s, t) corners."""
        a, b = self.at(s0, t0), self.at(s1, t1)
        return box(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:24] or "passage"


def _span(spec: VenueSpec, wall: Wall) -> float:
    return spec.width_m if wall in ("north", "south") else spec.depth_m


def _origin(spec: VenueSpec, wall: Wall, along: float) -> tuple[float, float]:
    W, D = spec.width_m, spec.depth_m
    return {
        "north": (along, D),
        "south": (along, 0.0),
        "east": (W, along),
        "west": (0.0, along),
    }[wall]


def _exit_rect(
    p: PassagePart, e: PassageExitSpec, s0: float, length: float, width: float
) -> tuple[Polygon, float] | None:
    """An exit on a side or across the far end of the stretch s0..s0+length of width `width`,
    and its width (an exit never spans more than the wall it is on)."""
    w = round(min(e.width_m, (length if e.side != "end" else width) - 0.2), 2)
    if w < 0.8:
        return None
    if e.side == "end":
        s1 = s0 + length - INSET_M
        return p.box(s1 - EXIT_DEPTH_M, s1, -w / 2, w / 2), w
    sc = s0 + min(max(e.at * length, w / 2 + 0.1), length - w / 2 - 0.1)
    edge = width / 2 - INSET_M
    t0, t1 = (edge - EXIT_DEPTH_M, edge) if e.side == "left" else (-edge, -edge + EXIT_DEPTH_M)
    return p.box(sc - w / 2, sc + w / 2, t0, t1), w


def solve_passages(
    spec: VenueSpec, problems: list[str], notes: list[str], assumptions: list[str]
) -> list[PassagePart]:
    """Passages (and their end areas) in venue coordinates, with their exits and narrowings."""
    out: list[PassagePart] = []
    used: list[Polygon] = [box(0, 0, spec.width_m, spec.depth_m)]
    ids: set[str] = set()
    for ps in spec.passages:
        span = _span(spec, ps.wall)
        if ps.width_m > span:
            problems.append(
                f"“{ps.label}” is {ps.width_m:g} m wide but the {ps.wall} wall is only {span:g} m "
                "long: make the main floor wider or the passage narrower."
            )
            continue
        half = ps.width_m / 2
        along = min(max(ps.position * span, half), span - half)
        fwd, left = _FRAME[ps.wall]
        part = PassagePart(
            spec=ps,
            origin=_origin(spec, ps.wall, along),
            out=fwd,
            left=left,
            strip=Polygon(),
            area=None,
            opening=Polygon(),
        )
        part.strip = part.box(0, ps.length_m, -half, half)
        part.opening = part.box(-2.0, 0.0, -half - 0.5, half + 0.5)
        if ps.end_area is not None:
            a = ps.end_area
            part.area = part.box(
                ps.length_m, ps.length_m + a.depth_m, -a.width_m / 2, a.width_m / 2
            )
        shape = part.strip if part.area is None else part.strip.union(part.area)
        if any(shape.intersection(u).area > 1e-6 for u in used[1:]) or (
            shape.intersection(used[0]).area > 1e-6
        ):
            problems.append(
                f"“{ps.label}” runs into another passage or back into the main floor: "
                "put it on another wall or position."
            )
            continue
        used.append(shape.buffer(0.5))
        base = slug(ps.label)
        n = 1
        while base in ids:
            n += 1
            base = f"{slug(ps.label)}_{n}"
        ids.add(base)
        _passage_exits(part, base, problems, notes)
        if ps.narrowing is not None:
            nw = ps.narrowing
            if nw.width_m < ps.width_m - 0.2:
                sc = min(max(nw.at * ps.length_m, nw.length_m / 2), ps.length_m - nw.length_m / 2)
                s0, s1 = sc - nw.length_m / 2, sc + nw.length_m / 2
                label = nw.label or f"Narrowing to {nw.width_m:g} m"
                for side, (t0, t1) in (
                    ("l", (nw.width_m / 2, half + 0.05)),
                    ("r", (-half - 0.05, -nw.width_m / 2)),
                ):
                    part.obstacles.append(
                        Obstacle(
                            id=f"{base}_narrow_{side}",
                            kind="fence",
                            polygon=geo.to_points(part.box(s0, s1, t0, t1)),
                            height_m=1.2,
                            label=label,
                        )
                    )
            else:
                notes.append(f"The narrowing of “{ps.label}” is as wide as the passage; left out.")
        out.append(part)
    if any(re.search(r"ramp|slope|incline|stair", p.spec.label, re.I) for p in out):
        assumptions.append(
            "Ramps and slopes are drawn flat: the simulation does not model the incline."
        )
    return out


def _passage_exits(part: PassagePart, base: str, problems: list[str], notes: list[str]) -> None:
    ps = part.spec
    counts = {"left": 0, "right": 0, "end": 0}
    for e in ps.exits:
        if e.side == "end" and part.area is not None:
            notes.append(
                f"“{ps.label}” ends in “{ps.end_area.label if ps.end_area else ''}”, so its end "
                "exit was put on the far side of that area."
            )
        stretch = (0.0, ps.length_m, ps.width_m)
        if e.side == "end" and part.area is not None and ps.end_area is not None:
            stretch = (ps.length_m, ps.end_area.depth_m, ps.end_area.width_m)
        got = _exit_rect(part, e, *stretch)
        counts[e.side] += 1
        if got is None:
            problems.append(f"No room for the {e.side} exit of “{ps.label}”: make it narrower.")
            continue
        label = e.label or f"{ps.label} {'end' if e.side == 'end' else e.side + ' exit'}"
        part.exits.append(
            Exit(
                id=f"{base}_{e.side}{counts[e.side]}",
                polygon=geo.to_points(got[0]),
                width_m=got[1],
                label=label,
            )
        )
    if ps.end_area is not None:
        a = ps.end_area
        for k, e in enumerate(a.exits, start=1):
            got = _exit_rect(part, e, ps.length_m, a.depth_m, a.width_m)
            if got is None:
                problems.append(f"No room for exit {k} of “{a.label}”: make it narrower.")
                continue
            label = e.label or f"{a.label} {'far side' if e.side == 'end' else e.side + ' side'}"
            part.exits.append(
                Exit(
                    id=f"{base}_area_{e.side}{k}",
                    polygon=geo.to_points(got[0]),
                    width_m=got[1],
                    label=label,
                )
            )


def walkable_with(spec: VenueSpec, parts: list[PassagePart]) -> list[tuple[float, float]]:
    """The main floor plus every passage and end area, as one outline."""
    main = box(0, 0, spec.width_m, spec.depth_m)
    if not parts:
        return geo.rect(0, 0, spec.width_m, spec.depth_m)
    shapes = [main] + [p.strip if p.area is None else p.strip.union(p.area) for p in parts]
    # a hair of overlap so the union is one polygon without slivers
    merged = unary_union([s.buffer(0.001, join_style="mitre") for s in shapes]).buffer(
        -0.001, join_style="mitre"
    )
    return geo.to_points(geo.largest_part(merged).simplify(0.0005))


def dividers(spec: VenueSpec) -> list[Obstacle]:
    """Fences across the whole main floor."""
    out: list[Obstacle] = []
    for k, d in enumerate(spec.dividers, start=1):
        h = DIVIDER_M / 2
        if d.along == "north_south":
            x = d.position * spec.width_m
            poly = geo.rect(x - h, 0.0, x + h, spec.depth_m)
        else:
            y = d.position * spec.depth_m
            poly = geo.rect(0.0, y - h, spec.width_m, y + h)
        out.append(
            Obstacle(
                id=f"divider_{k}",
                kind="fence",
                polygon=poly,
                height_m=2.4,
                label=d.label or "Fence",
            )
        )
    return out


def area_shape(parts: list[PassagePart], label: str) -> Polygon | None:
    """Where people in a passage (or the area at its end) named `label` can stand."""
    key = label.strip().lower()
    for p in parts:
        if p.spec.label.strip().lower() == key:
            return p.strip
        if p.spec.end_area is not None and p.spec.end_area.label.strip().lower() == key:
            return p.area
    return None


def area_labels(parts: list[PassagePart]) -> list[str]:
    names = [p.spec.label for p in parts]
    names += [p.spec.end_area.label for p in parts if p.spec.end_area is not None]
    return names


def heading_exits(exits: list[Exit], heading: str) -> list[str]:
    """Exits whose label is `heading`, or starts with it (one name for several gates)."""
    key = heading.strip().lower()
    exact = [e.id for e in exits if (e.label or "").strip().lower() == key]
    if exact:
        return exact
    return [e.id for e in exits if (e.label or e.id).strip().lower().startswith(key)]


def clear_of(shape: Polygon, blockers: object) -> Polygon | None:
    """The largest part of `shape` outside `blockers`, or None if nothing usable is left."""
    area = shape.buffer(-0.3).difference(blockers)
    if area.is_empty or area.area < 2:
        return None
    return geo.largest_part(area).simplify(0.05)
