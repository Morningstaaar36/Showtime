"""The Tavily search adapter with a fake Tavily client (no key, no network): cache, call cap,
no key, offline mode and errors (step 4a)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from api.adapters.search import SearchBudget, TavilySearch


class FakeTavily:
    """Stands in for AsyncTavilyClient: canned results, and every call recorded."""

    def __init__(self, fail: bool = False) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail = fail

    async def search(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(("search", kw))
        if self.fail:
            raise RuntimeError("Tavily is down")
        return {
            "results": [
                {
                    "title": "Crowd crush at a stadium gate",
                    "url": "https://example.org/crush",
                    "content": "Fans were crushed at gate C when it was opened late.",
                    "published_date": "2023-05-01",
                    "score": 0.9,
                },
                {"title": "No url, dropped", "content": "x"},
            ]
        }

    async def extract(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(("extract", kw))
        return {"results": [{"url": kw["urls"][0], "raw_content": "Full page text."}]}


def _search(
    tmp_path: Path, key: str = "tv", offline: bool = False, fail: bool = False
) -> tuple[TavilySearch, FakeTavily]:
    fake = FakeTavily(fail)
    return TavilySearch(key, tmp_path, offline=offline, client=fake), fake


async def test_a_live_search_returns_cited_hits_and_caches_them(tmp_path: Path) -> None:
    s, fake = _search(tmp_path)
    hits = await s.search("stadium crush", max_results=3)
    assert [(h.title, h.url, h.source) for h in hits] == [
        ("Crowd crush at a stadium gate", "https://example.org/crush", "tavily")
    ]
    assert hits[0].published == "2023-05-01"
    again = await s.search("stadium crush", max_results=3)
    assert [h.source for h in again] == ["cache"] and len(fake.calls) == 1  # no second call


async def test_the_session_cap_stops_live_calls(tmp_path: Path) -> None:
    s, fake = _search(tmp_path)
    budget = SearchBudget(max_calls=1)
    assert await s.search("first", budget=budget)
    assert await s.search("second", budget=budget) == []
    assert len(fake.calls) == 1 and budget.used == 1


async def test_without_a_key_or_offline_it_never_calls_out(tmp_path: Path) -> None:
    for s, fake in (_search(tmp_path / "a", key=""), _search(tmp_path / "b", offline=True)):
        assert await s.search("anything") == [] and await s.extract(["https://x.org"]) == []
        assert fake.calls == []


async def test_an_error_returns_nothing_instead_of_failing(tmp_path: Path) -> None:
    s, fake = _search(tmp_path, fail=True)
    assert await s.search("anything") == []
    assert len(fake.calls) == 1


async def test_extract_is_cached_and_capped(tmp_path: Path) -> None:
    s, fake = _search(tmp_path)
    out = await s.extract(["https://example.org/crush"])
    assert out == [{"url": "https://example.org/crush", "content": "Full page text."}]
    assert await s.extract(["https://example.org/crush"]) == out and len(fake.calls) == 1


async def test_the_fake_search_provider_is_marked_as_test_data(tmp_path: Path) -> None:
    from api.adapters.providers import search_provider
    from api.core.settings import Settings

    s = Settings(_env_file=None, search_provider="fake", cache_dir=tmp_path)
    client = search_provider("fake").build(s)
    hits = await client.search("anything")
    assert client.live and hits[0].title.startswith("[test data]")
    assert hits[0].url.startswith("https://example.org/")


async def test_a_search_asks_for_publication_dates(tmp_path: Path) -> None:
    # Tavily returns published_date only when asked (include_published_date, default false);
    # the evidence panel shows each source's year from it
    s, fake = _search(tmp_path)
    await s.search("stadium crush")
    assert fake.calls[0][1]["include_published_date"] is True
