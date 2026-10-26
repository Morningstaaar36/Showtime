"""Evidence desk for the Brief and the Designer: what the web says about this place and this
kind of event (capacity, typical attendance, local crowd-safety rules), as cited suggestions the
organizer checks. Nothing here changes a number: a suggestion quotes its source and links to it.

Live only with a search provider that searches the web (Tavily with a key); otherwise empty.
"""

from __future__ import annotations

from typing import Any

from api.adapters.search import SearchBudget


def desk_queries(brief: Any, n: int) -> list[tuple[str, str]]:
    """(topic, query) pairs for the brief: the place's capacity and attendance when it names a
    real place, and the crowd-safety guidance for this kind of event."""
    kind = str(getattr(brief, "kind", "") or "event").replace("_", " ")
    place = str(getattr(brief, "place", "") or "").strip()
    out: list[tuple[str, str]] = []
    if place:
        out.append(("capacity", f"{place} capacity"))
        out.append(("attendance", f"{place} {kind} attendance crowd"))
    out.append(("rules", f"{kind} crowd safety guidance {place}".strip()))
    return out[: max(0, n)]


def _sentence(snippet: str) -> str:
    first = snippet.strip().replace("\n", " ").split(". ")[0]
    return (first if len(first) > 30 else snippet.strip())[:240]


async def evidence_desk(
    search: Any, brief: Any, settings: Any, budget: SearchBudget | None
) -> list[dict[str, Any]]:
    """Cited suggestions to check, each {topic, title, url, published, sentence}; [] when web
    search is off. Duplicate pages are listed once."""
    if not getattr(search, "live", False):
        return []
    domains = [d.strip() for d in str(settings.evidence_desk_domains).split(",") if d.strip()]
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for topic, q in desk_queries(brief, settings.evidence_desk_queries):
        hits = await search.search(
            q,
            max_results=settings.search_results_per_query,
            budget=budget,
            include_domains=domains or None,
        )
        for h in hits:
            if h.url in seen:
                continue
            seen.add(h.url)
            out.append(
                {
                    "topic": topic,
                    "title": h.title,
                    "url": h.url,
                    "published": h.published,
                    "sentence": _sentence(h.snippet),
                }
            )
    return out
