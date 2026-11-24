"""Lists held in JSON inside an HTML page (SPEC 7.9)."""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from brief.models import Entry, FetchContext, SourceError
from brief.normalise import strip_html

LONDON = ZoneInfo("Europe/London")


def _unjson(value: str) -> str:
    try:
        return json.loads('"' + value + '"')
    except json.JSONDecodeError:
        return value


def _date(text: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=LONDON)
    return dt.astimezone(timezone.utc)


def parse_page(text: str, ex: dict) -> list[Entry]:
    if ex.get("unescape_html"):
        text = html.unescape(text)
    out, seen = [], set()
    for m in re.finditer(ex["pattern"], text):
        url = _unjson(m.group("url"))
        if url in seen:
            continue
        seen.add(url)
        out.append(Entry(
            url=url,
            title=_unjson(m.group("title")),
            description=strip_html(_unjson(m.group("abstract"))),
            published=_date(m.group("date")),
        ))
    if not out:
        raise SourceError("0 items matched the pattern. The page layout may have changed.")
    return out


def fetch(source: dict, ctx: FetchContext) -> list[Entry]:
    url = source["url"]
    if not ctx.robots.allowed(url):
        raise SourceError("robots.txt disallows this page")
    resp = ctx.fetcher.get(url, accept="text/html")
    if resp is None:
        return []
    return parse_page(resp.text, source["extract"])
