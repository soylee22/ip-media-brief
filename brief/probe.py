"""Test sources without writing data (SPEC 18)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from brief import config
from brief.collect import fetch_all
from brief.http import Fetcher
from brief.models import FetchContext
from brief.robots import Robots


def run(only: list[str] | None = None, report: str | None = None, base: Path | None = None) -> list[dict]:
    base = base or config.root()
    settings = config.load_settings(base)
    sources = config.load_sources(base)
    if only:
        sources = [s for s in sources if s["id"] in set(only)]
    fetcher = Fetcher(settings)  # no cache file: probe never changes state
    ctx = FetchContext(fetcher=fetcher, robots=Robots(fetcher), mode="normal",
                       age_floor=datetime(2000, 1, 1, tzinfo=timezone.utc), max_pages=1,
                       known_ids=set(), settings=settings)
    results = fetch_all(sources, ctx, settings["collect"]["max_workers"])
    fetcher.close()
    rows = []
    for s in sources:
        res = results.get(s["id"])
        if isinstance(res, Exception):
            rows.append({"id": s["id"], "adapter": s["adapter"], "ok": False, "entries": 0,
                         "newest": "", "oldest": "", "error": str(res)[:150] or type(res).__name__})
            continue
        dates = [e.published for e in res if e.published]
        rows.append({"id": s["id"], "adapter": s["adapter"], "ok": True, "entries": len(res),
                     "newest": max(dates).date().isoformat() if dates else "",
                     "oldest": min(dates).date().isoformat() if dates else "", "error": ""})
    if report:
        ok = sum(1 for r in rows if r["ok"])
        lines = [f"## Probe: {ok} of {len(rows)} sources OK", "",
                 "| id | adapter | result | entries | newest | oldest | error |", "|---|---|---|---|---|---|---|"]
        for r in sorted(rows, key=lambda r: (r["ok"], r["id"])):
            lines.append(f"| `{r['id']}` | {r['adapter']} | {'OK' if r['ok'] else 'FAIL'} | {r['entries']} | "
                         f"{r['newest']} | {r['oldest']} | {r['error'].replace('|', '/')} |")
        Path(report).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows
