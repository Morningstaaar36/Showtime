"""Evacuation map (SVG): one plan per floor with exit-assignment arrows, hotspots and legend."""

from __future__ import annotations

import html
import math
from typing import Any

from pydantic import BaseModel

from api.core.extensions import Registry, ReportBundle
from api.core.extensions import geometry as geo
from api.models import Floor, Venue

INK, LINE, SIGNAL, EGRESS, CAUTION, DANGER, PLAN = (
    "#1C2329",
    "#8E9BA5",
    "#1F5FBF",
    "#0A7F4F",
    "#B97F00",
    "#C62828",
    "#EEF2F4",
)
FONT = "Public Sans, Helvetica, Arial, sans-serif"


class Config(BaseModel):
    """Drawing size."""

    panel_width_px: int = 760


def _esc(s: object) -> str:
    return html.escape(str(s), quote=True)


def _path(points: list[tuple[float, float]], tx: Any) -> str:
    return "M" + " L".join(f"{tx(x, y)[0]:.1f},{tx(x, y)[1]:.1f}" for x, y in points) + " Z"


def render_floor(
    venue: Venue,
    floor: Floor,
    assignment: dict[str, dict[str, int]],
    stair_assignment: dict[str, dict[str, int]],
    hotspots: list[Any],
    width: int,
) -> tuple[str, int]:
    """SVG group for one floor and its pixel height."""
    x0, y0, x1, y1 = geo.to_polygon(floor.walkable).bounds
    pad = 26.0
    scale = (width - 2 * pad) / max(x1 - x0, 1.0)
    height = int((y1 - y0) * scale + 2 * pad)

    def tx(x: float, y: float) -> tuple[float, float]:
        return (pad + (x - x0) * scale, pad + (y1 - y) * scale)

    out: list[str] = [f'<rect x="0" y="0" width="{width}" height="{height}" fill="{PLAN}"/>']
    out.append(
        f'<path d="{_path(floor.walkable, tx)}" fill="#FFFFFF" stroke="{INK}" stroke-width="2.4"/>'
    )
    for z in floor.zones:
        out.append(
            f'<path d="{_path(z.polygon, tx)}" fill="{SIGNAL}" fill-opacity="0.07" '
            f'stroke="{SIGNAL}" stroke-opacity="0.6" stroke-dasharray="5 4" stroke-width="1"/>'
        )
    for o in floor.obstacles:
        fill = INK if o.kind == "wall" else "#C5CED5" if o.kind == "stage" else "#DCE2E6"
        out.append(
            f'<path d="{_path(o.polygon, tx)}" fill="{fill}" stroke="{LINE}" stroke-width="0.8"/>'
        )
        if o.kind not in ("wall", "barrier", "fence"):
            cx, cy = tx(*geo.centroid(o.polygon))
            out.append(
                f'<text x="{cx:.1f}" y="{cy + 3:.1f}" font-size="9" text-anchor="middle" '
                f'fill="{INK}" font-family="{FONT}">{_esc(o.label or o.id)}</text>'
            )
    for s in venue.stairs:
        for poly, fid in ((s.top_polygon, s.from_floor), (s.bottom_polygon, s.to_floor)):
            if fid == floor.floor_id:
                out.append(
                    f'<path d="{_path(poly, tx)}" fill="#FFFFFF" stroke="{INK}" '
                    f'stroke-width="1" stroke-dasharray="2 2"/>'
                )
                cx, cy = tx(*geo.centroid(poly))
                out.append(
                    f'<text x="{cx:.1f}" y="{cy + 3:.1f}" font-size="9" text-anchor="middle" '
                    f'fill="{INK}" font-family="{FONT}">Stair</text>'
                )
    exits = {e.id: e for e in floor.exits}
    names = geo.display_names(venue)
    targets = dict(exits)
    for s in venue.stairs:
        if s.from_floor == floor.floor_id:
            targets[s.id] = s  # type: ignore[assignment]
    # arrows: zone -> exit (and stair bottom -> exit on the floor below)
    flows: list[tuple[tuple[float, float], str, int]] = []
    for z in floor.zones:
        for tid, n in assignment.get(z.id, {}).items():
            if tid in targets and n > 0:
                flows.append((geo.centroid(z.polygon), tid, n))
    for s in venue.stairs:
        if s.to_floor == floor.floor_id:
            for tid, n in stair_assignment.get(s.id, {}).items():
                if tid in exits and n > 0:
                    flows.append((geo.centroid(s.bottom_polygon), tid, n))
    max_n = max((n for _, _, n in flows), default=1)
    for (sx, sy), tid, n in flows:
        t = targets[tid]
        poly = t.polygon if hasattr(t, "polygon") else t.top_polygon  # type: ignore[union-attr]
        ex, ey = geo.centroid(poly)
        a, b = tx(sx, sy), tx(ex, ey)
        dx, dy = b[0] - a[0], b[1] - a[1]
        dist = math.hypot(dx, dy) or 1.0
        end = (b[0] - dx / dist * 10, b[1] - dy / dist * 10)
        w = 1.5 + 5.5 * n / max_n
        out.append(
            f'<line x1="{a[0]:.1f}" y1="{a[1]:.1f}" x2="{end[0]:.1f}" y2="{end[1]:.1f}" '
            f'stroke="{EGRESS}" stroke-width="{w:.1f}" stroke-opacity="0.75" '
            f'marker-end="url(#arrow)" stroke-linecap="round"/>'
        )
        mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
        out.append(
            f'<g><rect x="{mx - 18:.1f}" y="{my - 8:.1f}" width="36" height="15" rx="3" '
            f'fill="#FFFFFF" stroke="{EGRESS}" stroke-width="0.8"/>'
            f'<text x="{mx:.1f}" y="{my + 3:.1f}" font-size="9" text-anchor="middle" '
            f'fill="{EGRESS}" font-weight="600" font-family="{FONT}">{n:,}</text></g>'
        )
    for e in floor.exits:
        color = DANGER if e.blocked else EGRESS
        out.append(
            f'<path d="{_path(e.polygon, tx)}" fill="{color}" stroke="{color}" stroke-width="3"/>'
        )
        cx, cy = tx(*geo.centroid(e.polygon))
        label = f"{names.get(e.id, e.id)} · {e.width_m:g} m" + (" · BLOCKED" if e.blocked else "")
        half = len(label) * 2.9  # keep the label inside the drawing
        cx = min(max(cx, half + 4), width - half - 4)
        out.append(
            f'<text x="{cx:.1f}" y="{cy - 9:.1f}" font-size="10" text-anchor="middle" '
            f'font-weight="700" fill="{color}" font-family="{FONT}" paint-order="stroke" '
            f'stroke="#FFFFFF" stroke-width="3">{_esc(label)}</text>'
        )
    for h in hotspots:
        if h.floor_id != floor.floor_id:
            continue
        hx, hy = tx(h.x, h.y)
        color = DANGER if h.level == "danger" else CAUTION
        out.append(
            f'<circle cx="{hx:.1f}" cy="{hy:.1f}" r="11" fill="{color}" fill-opacity="0.18" '
            f'stroke="{color}" stroke-width="1.6"/>'
            f'<text x="{hx:.1f}" y="{hy + 3.5:.1f}" font-size="9" text-anchor="middle" '
            f'font-weight="700" fill="{color}" font-family="{FONT}">{h.peak_density_ppm2:.1f}</text>'
        )
    title = f"{floor.name or floor.floor_id}" + (
        f" · elevation {floor.elevation_m:g} m" if floor.elevation_m else ""
    )
    out.append(
        f'<text x="{pad}" y="16" font-size="12" font-weight="700" fill="{INK}" '
        f'font-family="{FONT}">{_esc(title)}</text>'
    )
    # scale bar
    bar_m = next(v for v in (5, 10, 20, 25, 50, 100) if v * scale >= 60)
    bx, by = width - pad - bar_m * scale, height - 10
    out.append(
        f'<rect x="{bx:.1f}" y="{by - 4:.1f}" width="{bar_m * scale / 2:.1f}" height="4" fill="{INK}"/>'
        f'<rect x="{bx + bar_m * scale / 2:.1f}" y="{by - 4:.1f}" width="{bar_m * scale / 2:.1f}" '
        f'height="4" fill="#FFFFFF" stroke="{INK}" stroke-width="0.8"/>'
        f'<text x="{bx + bar_m * scale:.1f}" y="{by - 7:.1f}" font-size="9" text-anchor="end" '
        f'fill="{INK}" font-family="{FONT}">{bar_m} m</text>'
    )
    return "\n".join(out), height


def render_map(bundle: ReportBundle, width: int = 760) -> str:
    """Complete SVG document (all floors stacked, title block, legend, disclaimer)."""
    venue = bundle.fixed_venue or bundle.venue
    run = bundle.final or bundle.baseline
    hotspots = (run.hotspots if run else [])[:6]
    parts: list[str] = []
    y = 70
    for f in sorted(venue.floors, key=lambda f: -f.elevation_m):
        g, h = render_floor(
            venue, f, bundle.exit_assignment, bundle.stair_assignment, hotspots, width
        )
        parts.append(f'<g transform="translate(0,{y})">{g}</g>')
        y += h + 14
    legend_y = y + 6
    total_h = legend_y + 92
    people = venue.total_people()
    head = (
        f'<text x="20" y="28" font-size="18" font-weight="700" fill="{INK}" font-family="{FONT}">'
        f"Evacuation map · {_esc(bundle.project_name)}</text>"
        f'<text x="20" y="48" font-size="11" fill="#55626D" font-family="{FONT}">'
        f"{_esc(venue.name)} · version {bundle.venue_version}"
        f"{' + red-team fixes' if bundle.fixed_venue else ''} · {people:,} people · "
        f"generated {_esc(bundle.generated_at)}</text>"
        f'<g transform="translate({width - 40},34)"><path d="M0,-16 L7,6 L0,1 L-7,6 Z" fill="{INK}"/>'
        f'<text x="0" y="20" font-size="10" text-anchor="middle" font-weight="700" fill="{INK}" '
        f'font-family="{FONT}">N</text></g>'
    )
    legend = (
        f'<g transform="translate(20,{legend_y})" font-family="{FONT}" font-size="10" fill="{INK}">'
        f'<line x1="0" y1="8" x2="34" y2="8" stroke="{EGRESS}" stroke-width="4" marker-end="url(#arrow)"/>'
        f'<text x="44" y="11">Planned route to an exit (width = people)</text>'
        f'<rect x="0" y="22" width="34" height="6" fill="{EGRESS}"/><text x="44" y="29">Exit</text>'
        f'<rect x="110" y="22" width="34" height="6" fill="{DANGER}"/><text x="154" y="29">Blocked exit</text>'
        f'<circle cx="17" cy="47" r="7" fill="{DANGER}" fill-opacity="0.18" stroke="{DANGER}"/>'
        f'<text x="44" y="50">Hotspot: peak people per m² ({_esc(run.run_id if run else "no run")})</text>'
        f'<text x="0" y="74" font-size="11" font-weight="700" fill="{DANGER}">{_esc(bundle.disclaimer)}'
        f"</text></g>"
    )
    defs = (
        f'<defs><marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" '
        f'markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{EGRESS}"/>'
        f"</marker></defs>"
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{total_h}" '
        f'viewBox="0 0 {width} {total_h}" role="img" aria-label="Evacuation map">'
        f'<rect width="100%" height="100%" fill="#FFFFFF"/>{defs}{head}{"".join(parts)}{legend}</svg>'
    )


class SvgMapExporter:
    """Exporter: evacuation map as SVG."""

    id = "export_svg_map"
    label = "Evacuation map (SVG)"
    media_type = "image/svg+xml"
    file_ext = "svg"

    def __init__(self, config: Config) -> None:
        self.config = config

    def render(self, bundle: ReportBundle) -> bytes:
        return render_map(bundle, self.config.panel_width_px).encode()


def showtime_register(registry: Registry, config: Config) -> None:
    """Register the exporter."""
    registry.add("Exporter", SvgMapExporter.id, SvgMapExporter(config))
