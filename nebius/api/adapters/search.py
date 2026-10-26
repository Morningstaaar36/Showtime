"""Web evidence provider: Tavily search + extract, disk-cached, with a per-session call cap.

Without a key (or offline) only cached results are served, and the UI shows
"Live search is off. Attack cards use the incident dataset."
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from api.adapters.cache import DiskCache, cache_key

log = logging.getLogger("showtime.search")


class SearchHit(BaseModel):
    """One web result. Agents may only cite URLs that came from hits."""

    title: str
    url: str
    snippet: str = ""
    published: str | None = None
    score: float | None = None
    source: str = "tavily"  # tavily | cache


@dataclass
class SearchBudget:
    """Live Tavily calls allowed in one session."""

    max_calls: int
    used: int = 0

    def take(self) -> bool:
        """Reserve one call; False when the cap is reached."""
        if self.used >= self.max_calls:
            return False
        self.used += 1
        return True


class TavilySearch:
    """Tavily client wrapper (https://docs.tavily.com)."""

    kind = "search"
    id = "tavily"
    label = "Tavily"

    def __init__(
        self, api_key: str, cache_dir: Path, offline: bool = False, client: Any | None = None
    ) -> None:
        self.api_key = api_key
        self.cache = DiskCache(cache_dir)
        self.offline = offline
        self._client = client
        self.live_calls = 0

    @property
    def live(self) -> bool:
        """True when live web search is available."""
        return bool(self.api_key) and not self.offline

    def _get_client(self) -> Any:
        if self._client is None:
            from tavily import AsyncTavilyClient

            self._client = AsyncTavilyClient(api_key=self.api_key)
        return self._client

    async def health(self) -> dict[str, Any]:
        if not self.api_key:
            return {"ok": True, "live": False, "detail": "Live search is off (no TAVILY_API_KEY)."}
        if self.offline:
            return {"ok": True, "live": False, "detail": "Live search is off (offline mode)."}
        return {"ok": True, "live": True, "detail": "Tavily key present"}

    async def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic",
        budget: SearchBudget | None = None,
        include_domains: list[str] | None = None,
    ) -> list[SearchHit]:
        """Cached search; live only when a key is set and the session budget allows."""
        params = {
            "q": query.strip(),
            "n": max_results,
            "depth": search_depth,
            "domains": include_domains or [],
        }
        key = cache_key("tavily.search", params)
        cached = self.cache.get(key)
        if cached is not None:
            return [SearchHit.model_validate({**h, "source": "cache"}) for h in cached]
        if not self.live or (budget is not None and not budget.take()):
            return []
        try:
            resp = await self._get_client().search(
                query=query,
                max_results=max_results,
                search_depth=search_depth,
                include_domains=include_domains or None,
                # published_date comes back only when asked (Tavily Search API, default false);
                # tavily-python 0.8.5 has no argument for it and passes extra fields through
                include_published_date=True,
            )
        except Exception as exc:
            log.warning("tavily search failed: %s", exc)
            return []
        self.live_calls += 1
        hits = [
            SearchHit(
                title=r.get("title") or r.get("url", ""),
                url=r["url"],
                snippet=(r.get("content") or "")[:600],
                published=r.get("published_date"),
                score=r.get("score"),
            )
            for r in resp.get("results", [])
            if r.get("url")
        ]
        self.cache.put(key, [h.model_dump() for h in hits])
        return hits

    async def extract(
        self, urls: list[str], budget: SearchBudget | None = None
    ) -> list[dict[str, str]]:
        """Page text for URLs (cached)."""
        key = cache_key("tavily.extract", sorted(urls))
        cached = self.cache.get(key)
        if cached is not None:
            return list(cached)
        if not self.live or (budget is not None and not budget.take()):
            return []
        try:
            resp = await self._get_client().extract(urls=urls)
        except Exception as exc:
            log.warning("tavily extract failed: %s", exc)
            return []
        self.live_calls += 1
        out = [
            {"url": r.get("url", ""), "content": (r.get("raw_content") or "")[:8000]}
            for r in resp.get("results", [])
        ]
        self.cache.put(key, out)
        return out
