"""Search: off. Evidence comes from the incident dataset only."""

from __future__ import annotations

from typing import Any

from api.adapters.providers import SEARCH
from api.adapters.providers.base import SearchProvider


def _build(s: Any) -> Any:
    from api.adapters.search import TavilySearch

    return TavilySearch("", s.cache_dir / "tavily", offline=True)  # never calls out


SEARCH.register(SearchProvider(kind="search", name="none", title="Web search off", build=_build))
