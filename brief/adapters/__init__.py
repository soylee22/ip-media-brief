"""Adapter registry and the shared paging rules (SPEC 7.2 and 7.3)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser

from brief.http import FetchError
from brief.models import Entry, FetchContext, SourceError
from brief.normalise import item_id

log = logging.getLogger("brief.adapters")


def struct_to_dt(t) -> datetime | None:
    if not t:
        return None
    try:
        return datetime(*t[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def page_url(url: str, style: str, n: int, backfill: bool = False) -> str:
    if style == "none" or (n == 1 and style != "blogger"):
        return url
    if style == "blogger" and n == 1 and not backfill:
        return url
    parts = urlsplit(url)
    query = parse_qsl(parts.query, keep_blank_values=True)
    if style == "wordpress":
        query = [(k, v) for k, v in query if k != "paged"] + [("paged", str(n))]
    elif style == "blogger":
        size = 150 if backfill else 25
        query = [(k, v) for k, v in query if k not in ("max-results", "start-index")]
        query += [("max-results", str(size)), ("start-index", str(1 + size * (n - 1)))]
    elif style == "fcl":
        query = [(k, v) for k, v in query if k != "page"] + [("page", str(n))]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def paged(source: dict, ctx: FetchContext, fetch_page: Callable[[int], list[Entry] | None]) -> list[Entry]:
    """Fetch page 1, then later pages until a stop rule applies."""
    style = source.get("paging", "none")
    max_pages = 1 if style == "none" else ctx.max_pages
    out: list[Entry] = []
    for n in range(1, max_pages + 1):
        try:
            entries = fetch_page(n)
        except (FetchError, SourceError) as exc:
            if n == 1:
                raise SourceError(str(exc)) from exc
            log.info("%s: paging stopped at page %d: %s", source["id"], n, exc)
            break
        if entries is None:  # 304 Not Modified
            break
        out.extend(entries)
        if not entries:
            break
        if any(item_id(e.url) in ctx.known_ids for e in entries):
            break
        dated = [e.published for e in entries if e.published]
        if dated and min(dated) < ctx.age_floor:
            break
    return out


def parse_feed(content: bytes) -> list[Entry]:
    feed = feedparser.parse(content)
    if not feed.entries and not feed.version:
        raise SourceError("response is not an RSS or Atom feed")
    out = []
    for e in feed.entries:
        link = e.get("link")
        title = e.get("title")
        if not link or not title:
            continue
        content_val = None
        if e.get("content"):
            content_val = e.content[0].get("value")
        out.append(Entry(
            url=link,
            title=title,
            description=e.get("summary"),
            content=content_val,
            published=struct_to_dt(e.get("published_parsed")),
            updated=struct_to_dt(e.get("updated_parsed")),
            publisher=(e.get("source") or {}).get("title"),
            extra={"author": e.get("author"), "id": e.get("id")},
        ))
    return out


def get_adapter(name: str):
    from brief.adapters import embedded_json, fcl, gnews, govuk, html_list, rss
    return {
        "rss": rss.fetch,
        "gnews": gnews.fetch,
        "govuk_search": govuk.fetch,
        "fcl": fcl.fetch,
        "html_list": html_list.fetch,
        "embedded_json": embedded_json.fetch,
    }[name]
