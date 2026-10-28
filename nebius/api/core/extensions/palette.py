"""Colours of printed and exported documents (report, checklist, evacuation map): the app's
base colours with safety colours dark enough for print contrast. One table for every exporter."""

from __future__ import annotations

PRINT: dict[str, str] = {
    "plan": "#F6F7FF",
    "ink": "#1D1B3A",
    "muted": "#55607A",
    "line": "#8E9BA5",
    "border": "#D7DBEE",
    "signal": "#5B4FF5",
    "egress": "#0F7A46",
    "caution": "#9A5B00",
    "danger": "#C62838",
}


def css_root() -> str:
    """The palette as CSS custom properties (`var(--egress)` …)."""
    return ":root{" + ";".join(f"--{k}:{v}" for k, v in PRINT.items()) + "}\n"
