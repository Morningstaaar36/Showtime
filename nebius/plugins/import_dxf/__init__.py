"""VenueImporter for DXF drawings using JuPedSim web-community layer names.

Layers (closed polylines, metres): `jps-walkable-areas` (outline), `jps-obstacles`,
`jps-exits`, `jps-distribution-areas` (zones; headcount from the area × people_per_m2).
"""

from __future__ import annotations

import io

from pydantic import BaseModel

from api.core.extensions import Registry
from api.core.extensions import geometry as geo
from api.models import Venue

LAYERS = {
    "walk": "jps-walkable-areas",
    "obst": "jps-obstacles",
    "exit": "jps-exits",
    "zone": "jps-distribution-areas",
}


class Config(BaseModel):
    people_per_m2: float = 1.5


def _polys(doc: object, layer: str) -> list[list[tuple[float, float]]]:
    out: list[list[tuple[float, float]]] = []
    msp = doc.modelspace()  # type: ignore[attr-defined]
    for ent in msp.query(f'LWPOLYLINE[layer=="{layer}"]'):
        pts = [(round(float(p[0]), 3), round(float(p[1]), 3)) for p in ent.get_points("xy")]
        if len(pts) >= 3:
            out.append(pts)
    for ent in msp.query(f'POLYLINE[layer=="{layer}"]'):
        pts = [
            (round(float(v.dxf.location.x), 3), round(float(v.dxf.location.y), 3))
            for v in ent.vertices
        ]
        if len(pts) >= 3:
            out.append(pts)
    return out


class DxfImporter:
    id = "import_dxf"
    label = "DXF drawing (JuPedSim layers)"
    file_extensions = (".dxf",)

    def __init__(self, config: Config) -> None:
        self.config = config

    def import_bytes(self, data: bytes, filename: str) -> Venue:
        import ezdxf

        try:
            doc = ezdxf.read(io.StringIO(data.decode("utf-8", errors="replace")))
        except Exception as exc:
            raise ValueError(f"{filename} could not be read as DXF: {exc}") from exc
        walk = _polys(doc, LAYERS["walk"])
        if not walk:
            raise ValueError(f"{filename} has no closed polyline on layer '{LAYERS['walk']}'.")
        outline = max(walk, key=lambda p: geo.to_polygon(p).area)
        exits = []
        for i, p in enumerate(_polys(doc, LAYERS["exit"])):
            x0, y0, x1, y1 = geo.to_polygon(p).bounds
            exits.append(
                {"id": f"exit_{i + 1}", "polygon": p, "width_m": round(max(x1 - x0, y1 - y0), 2)}
            )
        if not exits:
            raise ValueError(f"{filename} has no exits on layer '{LAYERS['exit']}'.")
        zones = [
            {
                "id": f"zone_{i + 1}",
                "polygon": p,
                "people": int(geo.to_polygon(p).area * self.config.people_per_m2),
            }
            for i, p in enumerate(_polys(doc, LAYERS["zone"]))
        ]
        obstacles = [
            {"id": f"obstacle_{i + 1}", "kind": "other", "polygon": p}
            for i, p in enumerate(_polys(doc, LAYERS["obst"]))
        ]
        name = filename.rsplit(".", 1)[0] or "Imported drawing"
        return Venue.model_validate(
            {
                "venue_id": "imported",
                "name": name,
                "mode": "indoor",
                "description": f"Imported from {filename}",
                "floors": [
                    {
                        "floor_id": "F0",
                        "name": "Ground floor",
                        "walkable": outline,
                        "obstacles": obstacles,
                        "exits": exits,
                        "zones": zones,
                    }
                ],
            }
        )


def showtime_register(registry: Registry, config: Config) -> None:
    registry.add("VenueImporter", DxfImporter.id, DxfImporter(config))
