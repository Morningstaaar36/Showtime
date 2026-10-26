"""OpenStreetMap data: place search (Nominatim), map features (Overpass), vector tiles (fallback).

All free community services with usage policies: identify the app, be gentle, cache everything.
https://operations.osmfoundation.org/policies/nominatim/ ·
https://wiki.openstreetmap.org/wiki/Overpass_API · https://openfreemap.org
Public Overpass servers are often busy (HTTP 504), so queries go to several backends at once
and the first good answer wins; if all fail, buildings, water, parks and roads come from
OpenFreeMap vector tiles (a CDN, but thinned out in dense cities). Data © OpenStreetMap
contributors, ODbL.
"""

from __future__ import annotations

import asyncio
import gzip
import logging
import math
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import httpx
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union

from api.adapters.cache import DiskCache, cache_key

log = logging.getLogger("showtime.osm")

USER_AGENT = "Showtime/0.1 (crowd-safety planning studio; local install)"
KM_PER_DEG_LAT = 111.32  # one degree of latitude, in km
ATTRIBUTION = "© OpenStreetMap contributors (ODbL)"
QUERY_VERSION = 4  # bump when a query changes (part of the cache key)
# Tried together; the first good answer wins. lz4/z are the two machines behind overpass-api.de.
TILE_Z = 14

_AREA_FILTER = (
    '["leisure"~"park|pitch|stadium|sports_centre|playground|garden|track|common"]',
    '["amenity"~"university|school|college|parking|marketplace|place_of_worship|hospital"]',
    '["landuse"~"recreation_ground|grass|religious|education|village_green"]',
    '["place"="square"]',
)


class OsmUnavailable(Exception):
    """The OSM services could not answer (offline, rate limited, too large)."""


class OpenStreetMap:
    """Search, features in a box, and the building or area under a point. Cached on disk."""

    kind = "osm"
    id = "openstreetmap"
    label = "OpenStreetMap"

    def __init__(
        self,
        nominatim_url: str,
        overpass_url: str,
        cache_dir: Path,
        offline: bool = False,
        timeout_s: float = 25.0,
        *,
        fallback_urls: Sequence[str] = (),
        late_urls: Sequence[str] = (),
        tiles_url: str,
        max_span_km: float,
    ) -> None:
        self.nominatim_url = nominatim_url.rstrip("/")
        servers = [overpass_url, *fallback_urls]
        self.overpass_urls = list(dict.fromkeys(servers))  # configured one first, no duplicates
        self.late_urls = list(late_urls)
        self.tiles_url = tiles_url
        self.max_span_km = max_span_km
        self.cache = DiskCache(cache_dir)
        self.offline = offline
        self.timeout_s = timeout_s
        self._nominatim_lock = asyncio.Lock()
        self._last = 0.0
        self._tile_url: str | None = None

    # ------------------------------------------------------------------ Nominatim

    async def _nominatim(self, path: str, params: dict[str, Any]) -> Any:
        if self.offline:
            raise OsmUnavailable("Map search is off (offline mode).")
        async with self._nominatim_lock:  # policy: at most one request per second
            wait = 1.0 - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                async with httpx.AsyncClient(
                    timeout=15.0, headers={"User-Agent": USER_AGENT}
                ) as client:
                    resp = await client.get(f"{self.nominatim_url}/{path}", params=params)
            except httpx.HTTPError as exc:
                raise OsmUnavailable(f"Place search could not be reached: {exc}") from exc
            finally:
                self._last = time.monotonic()
        if resp.status_code != 200:
            raise OsmUnavailable(f"Place search returned {resp.status_code}. Try again shortly.")
        return resp.json()

    async def search(self, query: str, limit: int = 6) -> list[dict[str, Any]]:
        """Places matching a free-text query: name, lat, lon, bbox and the outline if any."""
        params = {
            "q": query.strip()[:200],
            "format": "jsonv2",
            "limit": limit,
            "polygon_geojson": 1,
            "polygon_threshold": 0.00002,
            "accept-language": "en",
        }
        key = cache_key("nominatim", params)
        hit = self.cache.get(key)
        if hit is not None:
            return list(hit["items"])
        data = await self._nominatim("search", params)
        items = []
        for d in data:
            s, n, w, e = (float(v) for v in d.get("boundingbox", [0, 0, 0, 0]))
            gj = d.get("geojson") or {}
            ring = None
            if gj.get("type") == "Polygon":
                ring = [[c[1], c[0]] for c in gj["coordinates"][0]]
            elif gj.get("type") == "MultiPolygon":
                biggest = max(gj["coordinates"], key=lambda p: len(p[0]))
                ring = [[c[1], c[0]] for c in biggest[0]]
            items.append(
                {
                    "name": d.get("name") or d.get("display_name", "").split(",")[0],
                    "display_name": d.get("display_name", ""),
                    "lat": float(d["lat"]),
                    "lon": float(d["lon"]),
                    "bbox": [s, w, n, e],
                    "kind": f"{d.get('category', '')}/{d.get('type', '')}",
                    "outline": ring,  # [[lat, lon], ...] when the place is an area
                }
            )
        self.cache.put(key, {"items": items})
        return items

    # ------------------------------------------------------------------ Overpass

    async def _overpass(self, query: str, budget_s: float = 30.0) -> dict[str, Any]:
        """Send to several servers; return the first JSON answer (others are cancelled)."""
        if self.offline:
            raise OsmUnavailable("Map data is off (offline mode).")
        errors: list[str] = []

        async def one(client: httpx.AsyncClient, url: str, delay: float) -> dict[str, Any]:
            if delay:
                await asyncio.sleep(delay)
            resp = await client.post(url, data={"data": query})
            if resp.status_code != 200:
                raise OsmUnavailable(f"{url.split('/')[2]} {resp.status_code}")
            data: dict[str, Any] = resp.json()
            return data

        async with httpx.AsyncClient(
            timeout=self.timeout_s, headers={"User-Agent": USER_AGENT}
        ) as client:
            tasks = [asyncio.create_task(one(client, u, 0.0)) for u in self.overpass_urls]
            tasks += [asyncio.create_task(one(client, u, 4.0)) for u in self.late_urls]
            try:
                for fut in asyncio.as_completed(tasks, timeout=budget_s):
                    try:
                        return await fut
                    except (OsmUnavailable, httpx.HTTPError, ValueError) as exc:
                        errors.append(str(exc)[:80])
            except TimeoutError:
                errors.append("timeout")
            finally:
                for t in tasks:
                    t.cancel()
        log.info("overpass failed on every server: %s", "; ".join(errors))
        raise OsmUnavailable("The OpenStreetMap servers are busy right now. Try again in a minute.")

    async def features(
        self, south: float, west: float, north: float, east: float
    ) -> dict[str, Any]:
        """Buildings, open areas, paths, fences, water and entrances inside a box (lat/lon)."""
        span = self.max_span_km / KM_PER_DEG_LAT
        if north - south > span or east - west > span * 1.5:
            raise OsmUnavailable(
                "Zoom in further: the area is too large to load "
                f"(at most {self.max_span_km:g} km across)."
            )
        bbox = ",".join(f"{v:.5f}" for v in (south, west, north, east))
        areas = "".join(f"way{f}({bbox});relation{f}({bbox});" for f in _AREA_FILTER)
        query = (
            f"[out:json][timeout:25];("
            f'way["building"]({bbox});relation["building"]({bbox});{areas}'
            f'way["area"="yes"]["highway"="pedestrian"]({bbox});way["highway"]({bbox});'
            f'way["barrier"~"fence|wall|retaining_wall|hedge"]({bbox});'
            f'way["natural"="water"]({bbox});relation["natural"="water"]({bbox});'
            f'node["entrance"]({bbox});node["barrier"~"gate|entrance|lift_gate|turnstile"]({bbox});'
            f");out geom qt 6000;"
        )
        key = cache_key("overpass", QUERY_VERSION, bbox)
        hit = self.cache.get(key)
        if hit is not None:
            return dict(hit)
        try:
            data = await self._overpass(query)
            source = "openstreetmap"
        except OsmUnavailable:
            data = {"elements": []}
            source = ""
        feats = [f for el in data.get("elements", []) if (f := _feature(el)) is not None]
        if not source:  # every Overpass server failed: thinner data from vector tiles
            feats = await self._tile_features(south, west, north, east)
            source = "vector-tiles"
        out: dict[str, Any] = {"features": feats, "attribution": ATTRIBUTION, "source": source}
        if source == "openstreetmap":
            self.cache.put(key, out)
        return out

    async def at_point(self, lat: float, lon: float) -> dict[str, Any]:
        """The building under a point, else the smallest open area containing it."""
        p = f"{lat:.6f},{lon:.6f}"
        pick = "".join(f"way(pivot.a){f};relation(pivot.a){f};" for f in _AREA_FILTER)
        query = (
            f"[out:json][timeout:20];"
            f'(way["building"](around:80,{p});relation["building"](around:80,{p}););out geom;'
            f"is_in({p})->.a;({pick});out geom;"
        )
        key = cache_key("overpass-at", QUERY_VERSION, round(lat, 5), round(lon, 5))
        hit = self.cache.get(key)
        if hit is None:
            data = await self._overpass(query, budget_s=25.0)
            hit = {"features": [f for el in data["elements"] if (f := _feature(el)) is not None]}
            self.cache.put(key, hit)
        best: dict[str, Any] | None = None
        best_rank = (9, math.inf)
        for f in hit["features"]:
            if f["kind"] not in ("building", "area") or not f["closed"]:
                continue
            if not _contains(f["coords"], lat, lon):
                continue
            rank = (0 if f["kind"] == "building" else 1, _area_deg2(f["coords"]))
            if rank < best_rank:
                best, best_rank = f, rank
        return {"selection": best, "attribution": ATTRIBUTION}

    # ------------------------------------------------------------------ vector tiles

    async def _tile_features(
        self, south: float, west: float, north: float, east: float
    ) -> list[dict[str, Any]]:
        """Fallback features from OpenFreeMap vector tiles (z14). Empty if unreachable."""
        try:
            import mapbox_vector_tile as mvt
        except ImportError:  # pragma: no cover - dependency is in pyproject
            return []
        n = 2**TILE_Z

        def tx(lon: float) -> int:
            return int((lon + 180) / 360 * n)

        def ty(lat: float) -> int:
            r = math.radians(lat)
            return int((1 - math.asinh(math.tan(r)) / math.pi) / 2 * n)

        tiles = [
            (x, y) for x in range(tx(west), tx(east) + 1) for y in range(ty(north), ty(south) + 1)
        ]
        if len(tiles) > 6:
            return []
        out: list[dict[str, Any]] = []
        try:
            async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": USER_AGENT}) as c:
                if self._tile_url is None:
                    self._tile_url = (await c.get(self.tiles_url)).json()["tiles"][0]
                for x, y in tiles:
                    key = cache_key("ofm-tile", self._tile_url, x, y)
                    raw_hit = self.cache.get(key)
                    if raw_hit is None:
                        url = self._tile_url.format(z=TILE_Z, x=x, y=y)
                        raw = (await c.get(url)).content
                        if raw[:2] == b"\x1f\x8b":
                            raw = gzip.decompress(raw)
                        layers = mvt.decode(raw, default_options={"y_coord_down": True})
                        raw_hit = {"features": _tile_to_features(layers, x, y, n)}
                        self.cache.put(key, raw_hit)
                    out.extend(raw_hit["features"])
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            log.info("vector tiles unavailable: %s", exc)
            return []
        box = Polygon([(west, south), (east, south), (east, north), (west, north)])
        return [
            f
            for f in out
            if LineString([(c[1], c[0]) for c in f["coords"]] or [(0, 0), (0, 0)]).intersects(box)
        ]


def _tile_to_features(layers: dict[str, Any], tx: int, ty: int, n: int) -> list[dict[str, Any]]:
    """Decoded MVT layers → feature dicts (same shape as Overpass features)."""

    def ll(px: float, py: float, extent: int) -> list[float]:
        lon = (tx + px / extent) / n * 360 - 180
        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (ty + py / extent) / n))))
        return [round(lat, 7), round(lon, 7)]

    def rings(geom: dict[str, Any]) -> list[list[list[float]]]:
        if geom["type"] == "Polygon":
            return [geom["coordinates"][0]]
        if geom["type"] == "MultiPolygon":
            return [p[0] for p in geom["coordinates"]]
        return []

    out: list[dict[str, Any]] = []
    for name in ("building", "water", "park", "landcover", "landuse", "transportation"):
        layer = layers.get(name)
        if not layer:
            continue
        ext = int(layer.get("extent", 4096))
        for i, f in enumerate(layer["features"]):
            props, geom = f.get("properties", {}), f["geometry"]
            fid = f"t{name[0]}{tx}_{ty}_{f.get('id', i)}"
            label = str(props.get("name:en") or props.get("name") or "")
            if name == "transportation":
                lines = (
                    [geom["coordinates"]]
                    if geom["type"] == "LineString"
                    else geom["coordinates"]
                    if geom["type"] == "MultiLineString"
                    else []
                )
                cls = str(props.get("subclass") or props.get("class") or "")
                hw = _TILE_HIGHWAY.get(cls, cls)
                for j, ln in enumerate(lines):
                    out.append({"id": f"{fid}_{j}", "kind": "path", "name": label,
                                "tags": {"highway": hw}, "closed": False,
                                "coords": [ll(px, py, ext) for px, py in ln]})  # fmt: skip
                continue
            cls = str(props.get("class", ""))
            if name == "building":
                kind, tags = "building", {"height": str(props.get("render_height", ""))}
            elif name == "water":
                kind, tags = "water", {"natural": "water"}
            elif name in ("landcover", "landuse") and cls not in _TILE_OPEN:
                continue
            else:
                kind, tags = "area", {"leisure": cls or "park"}
            for j, ring in enumerate(rings(geom)):
                coords = [ll(px, py, ext) for px, py in ring]
                if coords and coords[0] != coords[-1]:
                    coords.append(coords[0])
                if len(coords) >= 4:
                    out.append({"id": f"{fid}_{j}", "kind": kind, "name": label, "tags": tags,
                                "coords": coords, "closed": True})  # fmt: skip
    return out


_TILE_HIGHWAY = {"minor": "residential", "trunk": "primary", "motorway": "primary"}
_TILE_OPEN = {"grass", "park", "university", "school", "college", "stadium", "pitch", "playground",
              "recreation_ground"}  # fmt: skip


def _contains(ring: list[list[float]], lat: float, lon: float) -> bool:
    """Point in polygon (ray casting) on [lat, lon] rings."""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        yi, xi = ring[i]
        yj, xj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-15) + xi:
            inside = not inside
        j = i
    return inside


def _area_deg2(ring: list[list[float]]) -> float:
    pairs = zip(ring, ring[1:] + ring[:1], strict=True)
    return abs(sum(a[1] * b[0] - b[1] * a[0] for a, b in pairs)) / 2


_AREA_KEYS = ("leisure", "amenity", "landuse", "place")
_KEEP = (
    "building", "building:levels", "height", "highway", "width", "barrier", "entrance",
    "leisure", "amenity", "landuse", "place", "area", "name", "lanes", "access", "natural",
)  # fmt: skip


def _outer_ring(members: list[dict[str, Any]]) -> list[dict[str, float]] | None:
    """Outer ring of a multipolygon relation: member ways joined end to end (largest ring)."""
    lines = [
        LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
        for m in members
        if m.get("role") in ("outer", "") and len(m.get("geometry") or []) >= 2
    ]
    if not lines:
        return None
    polys = list(polygonize(unary_union(lines)))
    if not polys:
        return None
    big = max(polys, key=lambda p: p.area)
    return [{"lat": y, "lon": x} for x, y in big.exterior.coords]


def _feature(el: dict[str, Any]) -> dict[str, Any] | None:
    """Overpass element → {id, kind, name, tags, coords [[lat, lon]], closed}."""
    tags = el.get("tags") or {}
    fid = f"{el['type'][0]}{el['id']}"
    name = tags.get("name:en") or tags.get("name") or tags.get("ref") or ""
    keep = {k: v for k, v in tags.items() if k in _KEEP}
    if el["type"] == "node":
        gate = tags.get("barrier") in ("gate", "entrance", "lift_gate", "turnstile")
        if "entrance" not in tags and not gate:
            return None
        return {"id": fid, "kind": "entrance", "name": name, "tags": keep,
                "coords": [[el["lat"], el["lon"]]], "closed": False}  # fmt: skip
    if el["type"] == "relation":
        geom = _outer_ring(el.get("members", []))
        if geom is None:
            return None
    else:
        geom = el.get("geometry") or []
    coords = [[round(p["lat"], 7), round(p["lon"], 7)] for p in geom]
    if len(coords) < 2:
        return None
    closed = len(coords) >= 4 and coords[0] == coords[-1]
    if "building" in tags and closed:
        kind = "building"
    elif tags.get("natural") == "water" and closed:
        kind = "water"
    elif closed and (any(k in tags for k in _AREA_KEYS) or tags.get("area") == "yes"):
        kind = "area"  # a campus mapped with a boundary wall is still the campus
    elif "barrier" in tags:
        kind = "barrier"
    elif "highway" in tags:
        kind = "path"
    else:
        return None
    return {"id": fid, "kind": kind, "name": name, "tags": keep, "coords": coords, "closed": closed}
