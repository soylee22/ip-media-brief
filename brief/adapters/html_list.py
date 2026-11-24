"""HTML list pages with CSS selectors (SPEC 7.8)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from brief.models import Entry, FetchContext, SourceError

LONDON = ZoneInfo("Europe/London")


def london_date(text: str, fmt: str) -> datetime | None:
    try:
        day = datetime.strptime(text.strip(), fmt)
    except ValueError:
        return None
    return day.replace(hour=9, tzinfo=LONDON).astimezone(timezone.utc)


def parse_page(html: str, base_url: str, ex: dict) -> list[Entry]:
    soup = BeautifulSoup(html, "lxml")
    elements = soup.select(ex["item"])
    if not elements:
        raise SourceError("0 items matched the item selector. The page layout may have changed.")
    out, seen = [], set()
    for el in elements:
        link_el = el if ex.get("link", "self") == "self" else el.select_one(ex["link"])
        title_el = el if ex.get("title", "self") == "self" else el.select_one(ex["title"])
        if link_el is None or title_el is None or not link_el.get("href"):
            continue
        url = urljoin(base_url, link_el["href"])
        title = re.sub(r"\s+", " ", title_el.get_text(" ")).strip()
        if ex.get("title_strip_regex"):
            title = re.sub(ex["title_strip_regex"], "", title).strip()
        if len(title) < 15 or url in seen:
            continue
        seen.add(url)
        published = None
        if ex.get("date_regex"):
            m = re.search(ex["date_regex"], el.get_text(" "))
            if m:
                published = london_date(m.group(1), ex.get("date_format", "%d %B %Y"))
        out.append(Entry(url=url, title=title, published=published))
    return out


def fetch(source: dict, ctx: FetchContext) -> list[Entry]:
    url = source["url"]
    if not ctx.robots.allowed(url):
        raise SourceError("robots.txt disallows this page")
    resp = ctx.fetcher.get(url, accept="text/html")
    if resp is None:
        return []
    return parse_page(resp.text, str(resp.url), source["extract"])
