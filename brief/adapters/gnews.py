"""Google News search feeds for blocked or feedless sites (SPEC 7.5)."""
from __future__ import annotations

from urllib.parse import quote_plus

from brief.adapters import parse_feed
from brief.models import Entry, FetchContext

BASE = "https://news.google.com/rss/search?q={q}&hl=en-GB&gl=GB&ceid=GB:en"


def build_url(query: str) -> str:
    return BASE.format(q=quote_plus(query))


def strip_publisher(title: str, publisher: str | None) -> str:
    if publisher:
        suffix = f" - {publisher}"
        if title.endswith(suffix):
            return title[: -len(suffix)].rstrip()
    return title


def fetch(source: dict, ctx: FetchContext) -> list[Entry]:
    resp = ctx.fetcher.get(build_url(source["query"]), conditional=True)
    if resp is None:
        return []
    entries = parse_feed(resp.content)
    for e in entries:
        e.title = strip_publisher(e.title, e.publisher)
        e.description = None
        e.content = None
    return entries
