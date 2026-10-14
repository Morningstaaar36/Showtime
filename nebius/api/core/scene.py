"""Inspection of the canonical Venue, independent of AI and simulation providers.

Connectivity uses every positive-area free-space component. Route lengths use a
bounded visibility graph, without nearest-cell snapping or geometry repairs.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
from collections import deque
from dataclasses import dataclass
from typing import Any

import networkx as nx
from pydantic import ValidationError
from shapely.geometry import LineString, Polygon
from shapely.geometry.base import BaseGeometry

from api.core.extensions import geometry as geo
from api.core.geometry import validate_venue
from api.core.venue_ops import venue_hash
from api.models.scene import (
    ComponentFacts,
    ExitFacts,
    FloorFacts,
    InputProvenance,
    PolygonSurface,
    RouteFacts,
    SceneFacts,
    SceneIdentity,
    SceneMetadata,
    SceneObject,
    SceneObjectKind,
    SceneSnapshot,
    SpatialIssue,
    StairFacts,
    ZoneFacts,
    ZonePartFacts,
    ZonePlacement,
    ZoneReachability,
)
from api.models.venue import Venue

MAX_ROUTE_NODES_PER_COMPONENT = 256
MAX_VISIBILITY_CHECKS = 80_000
AREA_EPSILON_M2 = 1e-9
Node = tuple[str, float, float]


class SceneInputError(ValueError):
    def __init__(self, issues: list[SpatialIssue]) -> None:
        super().__init__(issues[0].message)
        self.issues = issues


def _objects(venue: Venue) -> list[tuple[str, SceneObjectKind, str | None, Any]]:
    items: list[tuple[str, SceneObjectKind, str | None, Any]] = []
    for floor in venue.floors:
        items.append((floor.floor_id, "floor", floor.floor_id, floor))
        groups: list[tuple[SceneObjectKind, list[Any]]] = [
            ("obstacle", floor.obstacles),
            ("exit", floor.exits),
            ("zone", floor.zones),
        ]
        for kind, objects in groups:
            items.extend((obj.id, kind, floor.floor_id, obj) for obj in objects)
    items.extend((stair.id, "stair", None, stair) for stair in venue.stairs)
    return items


def _validate_input(venue: Venue) -> SceneMetadata:
    """Reject ambiguous identifiers and invalid polygons before any repair helper."""
    issues: list[SpatialIssue] = []

    def problem(code: str, message: str, target: str) -> None:
        issues.append(
            SpatialIssue(code=code, severity="error", message=message, target_ids=[target])
        )

    seen: set[str] = set()
    objects = _objects(venue)
    for oid, kind, _, obj in objects:
        if not oid.strip() or oid in seen:
            problem("invalid_object_id", f"Object ID '{oid}' is empty or duplicated.", oid)
        seen.add(oid)
        polygons = (
            [obj.walkable]
            if kind == "floor"
            else [obj.top_polygon, obj.bottom_polygon]
            if kind == "stair"
            else [obj.polygon]
        )
        for points in polygons:
            if len(points) < 3:
                problem("invalid_polygon", f"'{oid}' needs at least three polygon points.", oid)
                continue
            if not all(math.isfinite(x) and math.isfinite(y) for x, y in points):
                problem("non_finite_geometry", f"'{oid}' has non-finite coordinates.", oid)
                continue
            polygon = Polygon(points)
            if (
                not polygon.is_valid
                or polygon.is_empty
                or not math.isfinite(polygon.area)
                or polygon.area <= AREA_EPSILON_M2
            ):
                problem("invalid_polygon", f"'{oid}' needs a valid, nonzero-area polygon.", oid)
        for name in ("elevation_m", "height_m", "width_m", "length_m"):
            value = getattr(obj, name, None)
            if value is not None and not math.isfinite(value):
                problem("non_finite_dimension", f"'{oid}.{name}' must be finite.", oid)
    floors = {floor.floor_id for floor in venue.floors}
    for stair in venue.stairs:
        if stair.from_floor not in floors or stair.to_floor not in floors:
            problem(
                "unknown_stair_floor", f"Stair '{stair.id}' references an unknown floor.", stair.id
            )
    if venue.schema_version != 1:
        problem(
            "unsupported_scene_schema", "Only Venue schema version 1 is supported.", venue.venue_id
        )
    try:
        metadata = SceneMetadata.model_validate(venue.extensions.get("scene_metadata", {}))
    except ValidationError as exc:
        problem("invalid_scene_metadata", str(exc), venue.venue_id)
        metadata = SceneMetadata()
    for oid in metadata.objects.keys() | metadata.fields.keys():
        if oid not in seen:
            problem(
                "unknown_provenance_object", f"Provenance references unknown object '{oid}'.", oid
            )
    for oid, _, _, obj in objects:
        for name in metadata.fields.get(oid, {}):
            if name not in type(obj).model_fields:
                problem("unknown_provenance_field", f"Unknown field '{oid}.{name}'.", oid)
    if issues:
        raise SceneInputError(issues)
    return metadata


def scene_snapshot(
    venue: Venue, *, project_id: str | None = None, version: int | None = None
) -> SceneSnapshot:
    """Full existing geometry, typed provenance, units, and reproducible identity."""
    metadata = _validate_input(venue)
    try:
        encoded = json.dumps(
            venue.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (ValueError, TypeError) as exc:
        raise SceneInputError(
            [
                SpatialIssue(
                    code="invalid_scene_json",
                    severity="error",
                    message="Scene data must be finite JSON.",
                )
            ]
        ) from exc
    identity = SceneIdentity(
        project_id=project_id,
        venue_id=venue.venue_id,
        venue_version=version,
        venue_schema_version=venue.schema_version,
        venue_hash=venue_hash(venue),
        scene_hash="sha256:" + hashlib.sha256(encoded.encode()).hexdigest(),
    )
    objects = [
        SceneObject(
            id=oid,
            kind=kind,
            floor_id=floor_id,
            provenance=metadata.objects.get(oid, InputProvenance()),
            fields=metadata.fields.get(oid, {}),
        )
        for oid, kind, floor_id, _ in _objects(venue)
    ]
    return SceneSnapshot(identity=identity, venue=venue, objects=objects, metadata=metadata)


def _polygons(geometry: BaseGeometry) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry] if geometry.area > AREA_EPSILON_M2 else []
    return [polygon for part in getattr(geometry, "geoms", []) for polygon in _polygons(part)]


def _point(geometry: BaseGeometry) -> tuple[float, float]:
    point = geometry.representative_point()
    return (float(point.x), float(point.y))


def _surface(polygon: Polygon) -> PolygonSurface:
    return PolygonSurface(
        exterior=list(polygon.exterior.coords)[:-1],
        holes=[list(ring.coords)[:-1] for ring in polygon.interiors],
    )


@dataclass
class _Component:
    id: str
    floor_id: str
    polygon: Polygon
    exits: list[str]
    downstream: list[str]


def _intersections(
    components: list[_Component], polygon: BaseGeometry
) -> list[tuple[_Component, BaseGeometry]]:
    return [
        (component, intersection)
        for component in components
        if (intersection := component.polygon.intersection(polygon)).area > AREA_EPSILON_M2
    ]


def _reachable(start: str, components: dict[str, _Component]) -> list[str]:
    seen: set[str] = set()
    exits: set[str] = set()
    todo = deque([start])
    while todo:
        cid = todo.popleft()
        if cid in seen:
            continue
        seen.add(cid)
        component = components[cid]
        exits.update(component.exits)
        todo.extend(component.downstream)
    return sorted(exits)


def _route_graph(
    components: dict[str, _Component],
    anchors: dict[str, set[tuple[float, float]]],
    stair_edges: list[tuple[Node, Node, float]],
) -> tuple[nx.DiGraph | None, str | None]:
    """All or nothing budget: never report a shortest route from a truncated graph."""
    points: dict[str, list[tuple[float, float]]] = {}
    checks = 0
    for cid, component in components.items():
        polygon = component.polygon
        vertices = set(polygon.exterior.coords)
        for ring in polygon.interiors:
            vertices.update(ring.coords)
        vertices.update(anchors.get(cid, set()))
        points[cid] = sorted(vertices)
        count = len(vertices)
        if count > MAX_ROUTE_NODES_PER_COMPONENT:
            return None, "component_node_budget_exceeded"
        checks += count * (count - 1) // 2
    if checks > MAX_VISIBILITY_CHECKS:
        return None, "visibility_check_budget_exceeded"
    graph = nx.DiGraph()
    for cid, route_vertices in points.items():
        polygon = components[cid].polygon
        graph.add_nodes_from((cid, x, y) for x, y in route_vertices)
        for a, b in itertools.combinations(route_vertices, 2):
            if polygon.covers(LineString([a, b])):
                na, nb = (cid, *a), (cid, *b)
                distance = math.dist(a, b)
                graph.add_edge(na, nb, weight=distance)
                graph.add_edge(nb, na, weight=distance)
    for start, end, distance in stair_edges:
        graph.add_edge(start, end, weight=distance)
    return graph, None


def inspect_scene(
    venue: Venue,
    *,
    project_id: str | None = None,
    version: int | None = None,
    include_routes: bool = True,
) -> SceneFacts:
    """Static geometric access; no capacities, disaster forecasts, or safety verdicts."""
    snapshot = scene_snapshot(venue, project_id=project_id, version=version)
    components: dict[str, _Component] = {}
    by_floor: dict[str, list[_Component]] = {}
    floors: list[FloorFacts] = []
    for floor in venue.floors:
        free = geo.free_space(floor)
        free_parts = sorted(_polygons(free), key=lambda p: (*p.bounds, p.area, p.normalize().wkb))
        local = [
            _Component(f"{floor.floor_id}:component:{i}", floor.floor_id, p, [], [])
            for i, p in enumerate(free_parts)
        ]
        by_floor[floor.floor_id] = local
        components.update((component.id, component) for component in local)
        walk_area = Polygon(floor.walkable).area
        floors.append(
            FloorFacts(
                floor_id=floor.floor_id,
                elevation_m=floor.elevation_m,
                walkable_area_m2=walk_area,
                obstacle_area_within_floor_m2=max(0.0, walk_area - free.area),
                usable_area_m2=free.area,
                component_ids=[component.id for component in local],
            )
        )
    anchors: dict[str, set[tuple[float, float]]] = {cid: set() for cid in components}
    exit_nodes: dict[str, list[Node]] = {}
    exits: list[ExitFacts] = []
    for floor in venue.floors:
        free = geo.free_space(floor)
        for exit_ in floor.exits:
            polygon = Polygon(exit_.polygon)
            contacts = _intersections(by_floor[floor.floor_id], polygon)
            usable = polygon.intersection(free).area
            fraction = usable / polygon.area
            available = not exit_.blocked and fraction >= 0.5 and bool(contacts)
            nodes: list[Node] = []
            if available:
                for component, intersection in contacts:
                    component.exits.append(exit_.id)
                    point = _point(intersection)
                    anchors[component.id].add(point)
                    nodes.append((component.id, *point))
            exit_nodes[exit_.id] = nodes
            distances = [polygon.distance(Polygon(obj.polygon)) for obj in floor.obstacles]
            exits.append(
                ExitFacts(
                    exit_id=exit_.id,
                    floor_id=floor.floor_id,
                    blocked=exit_.blocked,
                    available_in_geometry=available,
                    declared_width_m=exit_.width_m,
                    usable_area_m2=usable,
                    usable_area_fraction=fraction,
                    component_ids=[component.id for component, _ in contacts],
                    nearest_obstacle_distance_m=min(distances) if distances else None,
                )
            )
    stairs: list[StairFacts] = []
    stair_edges: list[tuple[Node, Node, float]] = []
    for stair in venue.stairs:
        top = _intersections(by_floor[stair.from_floor], Polygon(stair.top_polygon))
        bottom = _intersections(by_floor[stair.to_floor], Polygon(stair.bottom_polygon))
        for origin, top_part in top:
            for destination, bottom_part in bottom:
                if destination.id not in origin.downstream:
                    origin.downstream.append(destination.id)
                a, b = _point(top_part), _point(bottom_part)
                anchors[origin.id].add(a)
                anchors[destination.id].add(b)
                stair_edges.append(((origin.id, *a), (destination.id, *b), stair.length_m))
        stairs.append(
            StairFacts(
                stair_id=stair.id,
                from_floor=stair.from_floor,
                to_floor=stair.to_floor,
                from_component_ids=[component.id for component, _ in top],
                to_component_ids=[component.id for component, _ in bottom],
                connected=bool(top and bottom),
                declared_width_m=stair.width_m,
                declared_length_m=stair.length_m,
            )
        )
    reachable = {cid: _reachable(cid, components) for cid in components}
    zone_regions: dict[str, list[tuple[_Component, BaseGeometry]]] = {}
    for floor in venue.floors:
        for zone in floor.zones:
            contacts = _intersections(by_floor[floor.floor_id], Polygon(zone.polygon))
            zone_regions[zone.id] = contacts
            for component, intersection in contacts:
                anchors[component.id].add(_point(intersection))
    graph, budget_reason = (
        _route_graph(components, anchors, stair_edges)
        if include_routes
        else (None, "routes_disabled")
    )
    zones: list[ZoneFacts] = []
    for floor in venue.floors:
        for zone in floor.zones:
            contacts = zone_regions[zone.id]
            usable = sum(region.area for _, region in contacts)
            parts: list[ZonePartFacts] = []
            accessible = 0.0
            targets: set[str] = set()
            for component, region in contacts:
                point = _point(region)
                ids = reachable[component.id]
                targets.update(ids)
                if ids:
                    accessible += region.area
                route = RouteFacts(status="unreachable", reason="no_reachable_open_exit")
                if ids and graph is None:
                    route = RouteFacts(status="not_computed", reason=budget_reason)
                elif ids and graph is not None:
                    start = (component.id, *point)
                    lengths, paths = nx.single_source_dijkstra(graph, start)
                    choices = [
                        (lengths[node], eid, node)
                        for eid in ids
                        for node in exit_nodes[eid]
                        if node in lengths
                    ]
                    if choices:
                        distance, eid, node = min(choices)
                        route = RouteFacts(
                            status="computed",
                            exit_id=eid,
                            distance_m=distance,
                            waypoint_count=len(paths[node]),
                        )
                    else:
                        route = RouteFacts(status="not_computed", reason="no_visibility_graph_path")
                parts.append(
                    ZonePartFacts(
                        component_id=component.id,
                        usable_area_m2=region.area,
                        fraction_of_usable_zone_area=region.area / usable,
                        representative_point=point,
                        point_clearance_m=component.polygon.boundary.distance(
                            region.representative_point()
                        ),
                        reachable_exit_ids=ids,
                        route=route,
                    )
                )
            unreachable = max(0.0, usable - accessible)
            excluded = max(0.0, Polygon(zone.polygon).area - usable)
            placement: ZonePlacement = (
                "unplaced"
                if usable <= AREA_EPSILON_M2
                else "partially_placed"
                if excluded > AREA_EPSILON_M2
                else "fully_placed"
            )
            status: ZoneReachability = (
                "unplaced"
                if usable <= AREA_EPSILON_M2
                else "unreachable"
                if accessible <= AREA_EPSILON_M2
                else "partially_reachable"
                if unreachable > AREA_EPSILON_M2
                else "reachable"
            )
            zones.append(
                ZoneFacts(
                    zone_id=zone.id,
                    floor_id=floor.floor_id,
                    people=zone.people,
                    usable_area_m2=usable,
                    excluded_area_m2=excluded,
                    placement=placement,
                    reachable_area_m2=accessible,
                    unreachable_area_m2=unreachable,
                    reachability=status,
                    reachable_exit_ids=sorted(targets),
                    parts=parts,
                )
            )
    issues = [
        SpatialIssue(
            code=check.code,
            severity=check.severity,
            message=check.message,
            target_ids=check.target_ids,
            floor_id=check.floor_id,
        )
        for check in validate_venue(venue).checks
        if check.code != "zone_no_exit"
    ]
    for zone_fact in zones:
        if zone_fact.people and zone_fact.placement != "fully_placed":
            issues.append(
                SpatialIssue(
                    code="zone_demand_not_fully_placed",
                    severity="warning",
                    floor_id=zone_fact.floor_id,
                    target_ids=[zone_fact.zone_id],
                    message=f"Demand in '{zone_fact.zone_id}' is not fully placed; "
                    "reachability applies only to the modeled usable area.",
                )
            )
        if zone_fact.people and zone_fact.reachability == "unreachable":
            issues.append(
                SpatialIssue(
                    code="zone_no_exit",
                    severity="error",
                    floor_id=zone_fact.floor_id,
                    target_ids=[zone_fact.zone_id],
                    message=f"Occupied zone '{zone_fact.zone_id}' cannot reach an open exit.",
                )
            )
        if zone_fact.people and zone_fact.reachability == "partially_reachable":
            issues.append(
                SpatialIssue(
                    code="zone_partially_unreachable",
                    severity="error",
                    floor_id=zone_fact.floor_id,
                    target_ids=[zone_fact.zone_id],
                    message=f"Part of occupied zone '{zone_fact.zone_id}' "
                    "cannot reach an open exit.",
                )
            )
    return SceneFacts(
        identity=snapshot.identity,
        floors=floors,
        components=[
            ComponentFacts(
                component_id=component.id,
                floor_id=component.floor_id,
                area_m2=component.polygon.area,
                geometry=_surface(component.polygon),
                representative_point=_point(component.polygon),
                direct_exit_ids=sorted(component.exits),
                reachable_exit_ids=reachable[component.id],
                downstream_component_ids=sorted(component.downstream),
            )
            for component in components.values()
        ],
        exits=exits,
        stairs=stairs,
        zones=zones,
        issues=issues,
        routes_computed=graph is not None,
        route_budget_reason=budget_reason,
        limitations=[
            "Static polygon connectivity is not pedestrian capacity or a safety certification.",
            "Routes are from one representative point per zone/component to exit-area anchors; "
            "they do not measure every occupant's travel distance or evacuation time.",
            "Visibility paths permit boundary contact and have no body-radius constraint. "
            "Point clearance is distance to the free-space boundary at the reported point, "
            "not minimum corridor width or clearance along the entire route.",
            "Stairs are directed from from_floor to to_floor, with supplied stair length; "
            "stair geometry and crowd dynamics remain simplified.",
            "Area fractions do not allocate people to disconnected regions. "
            "Excluded zone area and any unassessed demand remain explicit.",
            "Exit availability reflects blocked state and polygon overlap, not verified "
            "permission, operability, or compliance with venue regulations.",
        ],
    )
