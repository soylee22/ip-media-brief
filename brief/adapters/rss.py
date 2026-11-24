"""RSS and Atom feeds (SPEC 7.4)."""
from __future__ import annotations

from brief.adapters import page_url, paged, parse_feed
from brief.models import Entry, FetchContext


def fetch(source: dict, ctx: FetchContext) -> list[Entry]:
    style = source.get("paging", "none")
    backfill = ctx.mode == "backfill"

    def page(n: int):
        url = page_url(source["url"], style, n, backfill)
        resp = ctx.fetcher.get(url, conditional=(n == 1))
        if resp is None:
            return None
        return parse_feed(resp.content)

    return paged(source, ctx, page)
