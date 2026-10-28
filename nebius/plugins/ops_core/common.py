"""Helpers shared by the edit operations (lookups, undo plumbing, annotations)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from api.models import PatchOpIn, Venue
from api.models.plan import ObjectConstraint, PlanData

Pt = tuple[float, float]


class _P(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: str


def _find(venue: Venue, target: str) -> tuple[int, str, int] | None:
    """(floor index, kind, item index) of an object id."""
    for fi, f in enumerate(venue.floors):
        groups: tuple[tuple[str, list[Any]], ...] = (
            ("obstacle", f.obstacles),
            ("exit", f.exits),
            ("zone", f.zones),
        )
        for kind, items in groups:
            for ii, it in enumerate(items):
                if it.id == target:
                    return fi, kind, ii
    return None


def _items(venue: Venue, fi: int, kind: str) -> list[Any]:
    f = venue.floors[fi]
    return {"obstacle": f.obstacles, "exit": f.exits, "zone": f.zones}[kind]  # type: ignore[return-value]


def _floor_index(venue: Venue, floor_id: str) -> int | None:
    for i, f in enumerate(venue.floors):
        if f.floor_id == floor_id:
            return i
    return None


def _id_taken(venue: Venue, new_id: str) -> bool:
    return new_id in venue.all_ids()


def _op(name: str, **kw: Any) -> PatchOpIn:
    return PatchOpIn.model_validate({"op": name, **{k: v for k, v in kw.items() if v is not None}})


def _insert(items: list[Any], index: int | None, item: Any) -> None:
    if index is None or index >= len(items):
        items.append(item)
    else:
        items.insert(index, item)


# --- object annotations (provenance, locks, existing/proposed) ---------------------
# Provenance goes to `scene_metadata`; locks and the
# existing/proposed distinction go to `plan_annotations`, which the scene contract does
# not validate. Removing an object drops its entries so no reference dangles.

METADATA_KEY = "scene_metadata"
ANNOTATIONS_KEY = "plan_annotations"
PLAN_KEY = "organizer_plan"


def _annotation_state(venue: Venue, target: str) -> dict[str, Any]:
    """Every stored annotation of one object (None where absent), for undo."""
    meta = venue.extensions.get(METADATA_KEY) or {}
    ann = venue.extensions.get(ANNOTATIONS_KEY) or {}
    state = {
        "provenance": (meta.get("objects") or {}).get(target),
        "fields": (meta.get("fields") or {}).get(target),
        "annotation": (ann.get("objects") or {}).get(target),
    }
    if PLAN_KEY in venue.extensions:
        data = PlanData.model_validate(venue.extensions[PLAN_KEY])
        policy = data.constraints.objects.get(target)
        state["policy"] = policy.model_dump(mode="json") if policy is not None else None
    return state


def _write_annotation_state(v: Venue, target: str, state: dict[str, Any]) -> None:
    """Set (or remove, where None) one object's entries in both extension sections."""
    ext = dict(v.extensions)
    for key, section, value in (
        (METADATA_KEY, "objects", state.get("provenance")),
        (METADATA_KEY, "fields", state.get("fields")),
        (ANNOTATIONS_KEY, "objects", state.get("annotation")),
    ):
        block = dict(ext.get(key) or {})
        entries = dict(block.get(section) or {})
        if value is None:
            entries.pop(target, None)
        else:
            entries[target] = value
        if entries:
            block[section] = entries
        else:
            block.pop(section, None)
        if any(k != "schema_version" for k in block):
            ext[key] = {"schema_version": 1, **block}
        else:
            ext.pop(key, None)
    v.extensions = ext
    if PLAN_KEY in ext and "policy" in state:
        data = PlanData.model_validate(ext[PLAN_KEY])
        if state["policy"] is None:
            data.constraints.objects.pop(target, None)
        else:
            data.constraints.objects[target] = ObjectConstraint.model_validate(state["policy"])
        v.extensions[PLAN_KEY] = data.model_dump(mode="json")


def _drop_annotations(v: Venue, target: str) -> None:
    _write_annotation_state(v, target, {})


def _restore_annotations(before: Venue, target: str) -> list[PatchOpIn]:
    """Inverse op that brings back a removed object's annotations (empty if it had none)."""
    state = _annotation_state(before, target)
    if all(value is None for value in state.values()):
        return []
    return [_op("set_annotation", target=target, restore=state)]
