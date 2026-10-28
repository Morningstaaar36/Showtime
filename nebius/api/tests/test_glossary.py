"""The glossary quotes the numbers this server uses, not numbers of its own."""

from __future__ import annotations

from api.core.glossary import glossary
from api.core.settings import Settings


def test_the_glossary_quotes_the_settings() -> None:
    text = " ".join(g["definition"] for g in glossary(Settings(_env_file=None)))
    assert "3.5 and above" in text and "{" not in text
    changed = " ".join(
        g["definition"]
        for g in glossary(Settings(_env_file=None, density_warn_ppm2=3.0, safety_factor=2.0))
    )
    assert "3 and above" in changed and "(2 here)" in changed
