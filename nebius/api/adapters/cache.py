"""Small JSON disk cache shared by adapters (weather, search, LLM record/replay)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger("showtime.cache")


def cache_key(*parts: Any) -> str:
    """sha256 over the JSON encoding of `parts` (stable key order)."""
    blob = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


class DiskCache:
    """One JSON file per key under `root`, written atomically."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._warned = False  # one warning per cache for a folder it cannot write

    def _path(self, key: str) -> Path:
        return self.root / key[:2] / f"{key}.json"

    def get(self, key: str) -> Any | None:
        """Cached value or None."""
        p = self._path(key)
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return None

    def put(self, key: str, value: Any) -> None:
        """Store a JSON-serialisable value. A cache is an optimisation: a folder it cannot write
        (owned by another user, a full disk) is logged once and the value is simply not kept."""
        p = self._path(key)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
            with os.fdopen(fd, "w") as fh:
                json.dump(value, fh)
            os.replace(tmp, p)
        except OSError as exc:
            if not self._warned:
                self._warned = True
                log.warning(
                    "cache %s: cannot write (%s); continuing without caching. If the folder "
                    "belongs to root (made by a container), run: make fix-perms",
                    self.root,
                    exc,
                )
