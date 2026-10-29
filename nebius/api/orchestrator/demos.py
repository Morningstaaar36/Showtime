"""Sample projects: precomputed demo packs in cache/demos/ are installed at start.

Each pack is tracked by content hash. A new or updated pack is installed; the sample it
replaces is removed only if the user never edited it; a sample the user deleted stays deleted.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import zipfile
from typing import Any

from api.core.settings import ROOT_DIR
from api.db.models import UserSetting
from api.db.session import db_session

log = logging.getLogger("showtime.demos")
DEMO_DIR = ROOT_DIR / "cache" / "demos"
STATE_KEY = "_installed_samples"


def _load(st: Any) -> dict[str, dict[str, Any]]:
    with db_session(st.projects.db_url) as s:
        row = s.get(UserSetting, STATE_KEY)
        return dict(row.value) if row and isinstance(row.value, dict) else {}


def _save(st: Any, state: dict[str, dict[str, Any]]) -> None:
    with db_session(st.projects.db_url) as s:
        row = s.get(UserSetting, STATE_KEY) or UserSetting(key=STATE_KEY)
        row.value = state
        s.add(row)
        s.commit()


def install_demos(st: Any) -> int:
    """Install new or updated demo packs; returns how many were installed."""
    state = _load(st)
    projects = {p.id: p for p in st.projects.list_projects(include_archived=True)}
    if not state:  # databases from before tracking: adopt existing samples by name
        for p in projects.values():
            if p.sample:
                state[f"legacy:{p.name}"] = {
                    "sha": "",
                    "project_id": p.id,
                    "version": 1,
                    "name": p.name,
                }
    n = 0
    for pack in sorted(DEMO_DIR.glob("*.showtime.zip")):
        data = pack.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        prev = state.get(pack.name)
        try:
            name = json.loads(zipfile.ZipFile(io.BytesIO(data)).read("project.json"))["name"]
        except (KeyError, zipfile.BadZipFile, json.JSONDecodeError):
            log.warning("skipping unreadable demo pack %s", pack.name)
            continue
        if prev is None:  # adopt a legacy install of the same sample
            legacy = state.pop(f"legacy:{name}", None)
            if legacy is not None:
                prev = state[pack.name] = legacy
        if prev is not None and prev.get("sha") == sha:
            continue  # up to date (or deliberately deleted by the user)
        old = projects.get(prev["project_id"]) if prev else None
        try:
            p = st.projects.import_zip(
                data,
                sample=True,
                runs_dir=st.settings.runs_dir,
                name=name,
                max_unpacked_bytes=st.settings.import_max_unpacked_bytes,
                max_entries=st.settings.import_max_entries,
            )
        except Exception:
            log.exception("could not install demo %s", pack.name)
            continue
        if old is not None and prev is not None and old.current_version == prev.get("version", 1):
            st.projects.delete(old.id, st.settings.runs_dir)  # unedited older copy of the sample
        state[pack.name] = {
            "sha": sha,
            "project_id": p.id,
            "version": p.current_version,
            "name": name,
        }
        n += 1
    state = {k: v for k, v in state.items() if not k.startswith("legacy:")}
    _save(st, state)
    if n:
        log.info("installed %d sample projects", n)
    return n
