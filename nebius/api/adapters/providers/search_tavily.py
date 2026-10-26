"""Search: Tavily web search with a disk cache and a per-session call cap. Not run live yet:
without TAVILY_API_KEY it is off and the red team uses the incident dataset."""

from __future__ import annotations

from typing import Any

from api.adapters.providers import SEARCH
from api.adapters.providers.base import Requirement, SearchProvider
from api.adapters.providers.checks import search_check


def _build(s: Any) -> Any:
    from api.adapters.search import TavilySearch

    return TavilySearch(s.tavily_api_key, s.cache_dir / "tavily", offline=s.offline)


SEARCH.register(
    SearchProvider(
        kind="search",
        name="tavily",
        title="Tavily web search",
        requirements=(
            Requirement("TAVILY_API_KEY", "tavily_api_key", "your Tavily API key", True),
        ),
        check_live=search_check,
        build=_build,
        live=True,
        citation="Web search results: Tavily",
        citation_url="https://tavily.com",
    )
)
