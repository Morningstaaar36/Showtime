"""Floor plans drawn as one image, for a model that reads images (the plan critic).

Each floor that differs is drawn to scale, side by side: walls and fixed features dark, the
kitchen and toilets in their own colours, tables as small squares, stairs green (the flight
with its treads, and its landings), exits
as bright green bars, and the people's areas outlined with their headcount. A legend and a scale
bar make it readable without the app.
"""

from __future__ import annotations

import base64
import io
from collections.abc import Sequence
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import MultiPoint, Polygon

from api.models import Venue

PX_PER_M = 22
PAD = 40
MAX_FLOORS = 3  # street level, the first floor above it, the top floor

_COLOURS = {
    "Table": (196, 150, 98),
    "Kitchen": (226, 116, 116),
    "Toilets": (116, 190, 226),
    "Lift": (150, 150, 150),
}
_WALL = (40, 44, 52)
_FLOOR = (238, 242, 246)
_ZONE = (90, 110, 230)
_STAIR = (24, 150, 70)
_FLIGHT = (200, 236, 210)
TREAD_M = 0.6  # drawing only: one line per this many metres of flight
_EXIT = (0, 200, 90)


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow without sized default fonts
        return ImageFont.load_default()


def drawn_floors(venue: Venue) -> list[int]:
    """Indexes of the floors to draw: street level, the first upper floor and the top one."""
    order = sorted(range(len(venue.floors)), key=lambda i: venue.floors[i].elevation_m)
    street = min(order, key=lambda i: abs(venue.floors[i].elevation_m))
    picks = [street]
    above = [i for i in order if venue.floors[i].elevation_m > venue.floors[street].elevation_m]
    below = [i for i in order if venue.floors[i].elevation_m < venue.floors[street].elevation_m]
    for i in above[:1] + above[-1:] + below[:1]:
        if i not in picks:
            picks.append(i)
    return picks[:MAX_FLOORS]


def _treads(
    d: ImageDraw.ImageDraw,
    top: Sequence[Sequence[float]],
    bottom: Sequence[Sequence[float]],
    T: Any,
) -> None:
    """Lines across a flight every TREAD_M, from one landing's centre to the other's."""
    a, b = Polygon(top).centroid, Polygon(bottom).centroid
    run = a.distance(b)
    if run < 0.5:
        return
    ux, uy = (b.x - a.x) / run, (b.y - a.y) / run
    half = 0.5 * min(Polygon(top).minimum_rotated_rectangle.length / 4, 1.5)
    for k in range(1, int(run / TREAD_M)):
        cx, cy = a.x + ux * k * TREAD_M, a.y + uy * k * TREAD_M
        d.line([T((cx - uy * half, cy + ux * half)), T((cx + uy * half, cy - ux * half))],
               fill=_STAIR, width=1)  # fmt: skip


def plan_png(venue: Venue) -> bytes:
    """The floor plans as one PNG."""
    picks = drawn_floors(venue)
    xs = [p[0] for f in venue.floors for p in f.walkable]
    ys = [p[1] for f in venue.floors for p in f.walkable]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    fw, fh = (x1 - x0) * PX_PER_M, (y1 - y0) * PX_PER_M
    width = int(len(picks) * (fw + PAD) + PAD)
    height = int(fh + 2 * PAD + 70)
    im = Image.new("RGB", (max(width, 520), height), "white")
    d = ImageDraw.Draw(im)
    small, label = _font(12), _font(15)
    for n, i in enumerate(picks):
        f = venue.floors[i]
        ox = PAD + n * (fw + PAD)

        def T(p: tuple[float, float] | list[float], ox: float = ox) -> tuple[float, float]:
            return (ox + (p[0] - x0) * PX_PER_M, PAD + 20 + (y1 - p[1]) * PX_PER_M)

        d.text((ox, 8), f.name or f.floor_id, fill="black", font=label)
        d.polygon([T(p) for p in f.walkable], fill=_FLOOR, outline=_WALL, width=3)
        for z in f.zones:
            d.polygon([T(p) for p in z.polygon], outline=_ZONE, width=1)
        for o in f.obstacles:
            colour = next((c for k, c in _COLOURS.items() if (o.label or "").startswith(k)), _WALL)
            d.polygon([T(p) for p in o.polygon], fill=colour)
        for s in venue.stairs:
            if f.floor_id not in (s.from_floor, s.to_floor):
                continue
            # the flight: the band from one landing to the other, with its treads drawn across
            flight = MultiPoint([*s.top_polygon, *s.bottom_polygon]).convex_hull
            if isinstance(flight, Polygon):
                d.polygon([T(p) for p in flight.exterior.coords], fill=_FLIGHT, outline=_STAIR)
                _treads(d, s.top_polygon, s.bottom_polygon, T)
                c = flight.centroid
                d.text(
                    T((c.x, c.y)), f"Stair {s.width_m:g} m", fill=_STAIR, font=small, anchor="mm"
                )
            for poly, fid in ((s.top_polygon, s.from_floor), (s.bottom_polygon, s.to_floor)):
                if fid == f.floor_id:
                    d.polygon([T(p) for p in poly], outline=_STAIR, width=3)
        for e in f.exits:
            d.polygon([T(p) for p in e.polygon], fill=_EXIT)
        people = sum(z.people for z in f.zones)
        d.text((ox, PAD + 26 + fh), f"{people} people", fill=_ZONE, font=small)
    # legend and a 5 m scale bar
    ly = height - 26
    lx = PAD
    for name, colour in [
        ("Wall", _WALL),
        *_COLOURS.items(),
        ("Stair (flight and landings)", _STAIR),
        ("Exit", _EXIT),
    ]:
        d.rectangle([lx, ly, lx + 12, ly + 12], fill=colour)
        d.text((lx + 16, ly - 1), name, fill="black", font=small)
        lx += 24 + int(d.textlength(name, font=small))
    d.line([lx + 10, ly + 6, lx + 10 + 5 * PX_PER_M, ly + 6], fill="black", width=3)
    d.text((lx + 14 + 5 * PX_PER_M, ly - 1), "5 m", fill="black", font=small)
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def plan_data_url(venue: Venue) -> str:
    """The floor plans as a PNG data URL (for a model's image input)."""
    return "data:image/png;base64," + base64.b64encode(plan_png(venue)).decode()
