"""GOV.UK search API (SPEC 7.6)."""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

from brief.adapters import paged
from brief.models import Entry, FetchContext, SourceError

SKIP_FORMATS = {"organisation", "person", "ministerial_role", "world_location"}
FIELDS = "title,link,description,public_timestamp,format"


def parse_time(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def build_url(source: dict, n: int) -> str:
    params = dict(source.get("params", {}))
    params.update({"order": "-public_timestamp", "count": 100, "start": 100 * (n - 1), "fields": FIELDS})
    return f"{source['url']}?{urlencode(params)}"


def fetch(source: dict, ctx: FetchContext) -> list[Entry]:
    def page(n: int):
        resp = ctx.fetcher.get(build_url(source, n), accept="application/json")
        try:
            data = resp.json()
        except ValueError as exc:
            raise SourceError("GOV.UK search did not return JSON") from exc
        out = []
        for r in data.get("results", []):
            if r.get("format") in SKIP_FORMATS or not r.get("link") or not r.get("title"):
                continue
            link = r["link"]
            url = link if link.startswith("http") else "https://www.gov.uk" + link
            out.append(Entry(url=url, title=r["title"], description=r.get("description"),
                             published=parse_time(r.get("public_timestamp"))))
        return out

    return paged(source, ctx, page)
