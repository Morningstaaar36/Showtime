"""Scaffold a plugin from plugins/_template: python scripts/new_plugin.py <ExtensionPoint> <id>."""

from __future__ import annotations

import re
import shutil
import sys

from api.core.extensions import EXTENSION_POINTS
from api.core.settings import ROOT_DIR


def main(kind: str, pid: str) -> int:
    if kind not in EXTENSION_POINTS:
        print(f"Unknown extension point {kind!r}. Choose one of: {', '.join(EXTENSION_POINTS)}")
        return 1
    if not re.fullmatch(r"[a-z][a-z0-9_]{2,40}", pid):
        print("Plugin id must be snake_case, e.g. hazard_flood")
        return 1
    dst = ROOT_DIR / "plugins" / pid
    if dst.exists():
        print(f"{dst} already exists")
        return 1
    shutil.copytree(ROOT_DIR / "plugins" / "_template", dst)
    name = pid.replace("_", " ").capitalize()
    for f in dst.iterdir():
        if f.is_file():
            f.write_text(
                f.read_text()
                .replace("__ID__", pid)
                .replace("__TYPE__", kind)
                .replace("__NAME__", name)
            )
    test = ROOT_DIR / "api" / "tests" / f"test_plugin_{pid}.py"
    test.write_text(
        f'''"""Tests for the {pid} plugin."""\n\nfrom api.core.plugins import PluginHost\n\n\n'''
        f"""def test_{pid}_loads(host: PluginHost) -> None:\n"""
        f'''    assert host.statuses["{pid}"].healthy\n'''
    )
    print(
        f"Created plugins/{pid}/ and {test.relative_to(ROOT_DIR)}. Enable it in config/features.yaml."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]) if len(sys.argv) >= 3 else 1)
