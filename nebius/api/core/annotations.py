"""Organizer annotations stored in venue extensions: provenance, locks, existing/proposed.

Provenance lives in `scene_metadata` (the P2-01 scene contract); locks and the
existing/proposed status live in `plan_annotations`. The `set_annotation` PatchOp in the
`ops_core` plugin writes both; plugins cannot import core helpers, so it keeps its own
copy of these two key names. They are part of the saved-venue contract.
"""

from __future__ import annotations

from typing import Any

from api.models import Venue

METADATA_KEY = "scene_metadata"
ANNOTATIONS_KEY = "plan_annotations"

# kinds that can be built: an opening or a barrier may exist already or be proposed
CONSTRUCTIBLE = ("exit", "obstacle")


def _prune(block: dict[str, Any], sections: tuple[str, ...], keep: set[str]) -> dict[str, Any]:
    """Drop entries of objects that no longer exist, and the block itself if empty."""
    out = dict(block)
    for section in sections:
        entries = {k: v for k, v in (out.get(section) or {}).items() if k in keep}
        if entries:
            out[section] = entries
        else:
            out.pop(section, None)
    return out if any(k != "schema_version" for k in out) else {}


def carry_annotations(current: Venue, fixed: Venue) -> Venue:
    """`fixed` geometry with `current`'s organizer data, ready to save as a new version.

    The red team's fixed venue was copied when the session started, so its name,
    description and extensions can be older than the current version's. Geometry comes
    from `fixed`; everything outside the simulation hash comes from `current`. Entries of
    removed objects are dropped (no dangling scene-metadata references) and exits or
    obstacles the fixes added are marked as proposed construction.
    """
    kinds = fixed.all_ids()
    keep = set(kinds)
    ext = dict(current.extensions)
    # Geometry bundles may remove constrained objects or introduce declared new
    # ones. Keep their validated typed plan rather than restoring the old copy.
    if "organizer_plan" in fixed.extensions:
        ext["organizer_plan"] = fixed.model_copy(deep=True).extensions["organizer_plan"]
    meta = _prune(ext.get(METADATA_KEY) or {}, ("objects", "fields"), keep)
    ann = _prune(ext.get(ANNOTATIONS_KEY) or {}, ("objects",), keep)
    added = [i for i, k in kinds.items() if k in CONSTRUCTIBLE and i not in current.all_ids()]
    if added:
        objects = dict(ann.get("objects") or {})
        for object_id in added:
            objects[object_id] = {"change": "proposed", **(objects.get(object_id) or {})}
        ann = {**ann, "objects": objects}
    for key, block in ((METADATA_KEY, meta), (ANNOTATIONS_KEY, ann)):
        if block:
            ext[key] = {"schema_version": 1, **block}
        else:
            ext.pop(key, None)
    return fixed.model_copy(
        update={"name": current.name, "description": current.description, "extensions": ext},
        deep=True,
    )
