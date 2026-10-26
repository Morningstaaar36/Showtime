"""Search: canned results for tests (SEARCH_PROVIDER=fake). Every result is marked as test data
and points at example.org, so it can never pass for real evidence."""

from __future__ import annotations

from typing import Any

from api.adapters.providers import SEARCH
from api.adapters.providers.base import SearchProvider


class _CannedTavily:
    """Answers like AsyncTavilyClient, from no network."""

    async def search(self, **kw: Any) -> dict[str, Any]:
        q = str(kw.get("query", ""))
        return {
            "results": [
                {
                    "title": f"[test data] result for: {q[:60]}",
                    "url": "https://example.org/test-result",
                    "content": "Test data from the fake search provider, not a real source.",
                }
            ]
        }

    async def extract(self, **kw: Any) -> dict[str, Any]:
        return {"results": [{"url": u, "raw_content": "[test data]"} for u in kw.get("urls", [])]}


def _build(s: Any) -> Any:
    from api.adapters.search import TavilySearch

    return TavilySearch("fake", s.cache_dir / "fake-search", client=_CannedTavily())


SEARCH.register(
    SearchProvider(kind="search", name="fake", title="Fake search (tests)", build=_build, live=True)
)
