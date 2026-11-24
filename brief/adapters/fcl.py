"""Find Case Law Atom feeds (SPEC 7.7). Never fetch judgment text (SPEC 21.2)."""
from __future__ import annotations

from brief.adapters import page_url, paged, parse_feed
from brief.models import Entry, FetchContext
from brief.normalise import find_citation


def fetch(source: dict, ctx: FetchContext) -> list[Entry]:
    def page(n: int):
        resp = ctx.fetcher.get(page_url(source["url"], "fcl", n), conditional=(n == 1))
        if resp is None:
            return None
        entries = parse_feed(resp.content)
        for e in entries:
            e.extra["court"] = e.extra.get("author")
            e.extra["citation"] = find_citation(e.title, e.description, e.extra.get("id"))
            e.content = None
        return entries

    return paged(source, ctx, page)
