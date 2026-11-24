"""Static site output (SPEC 13). No network requests."""
from __future__ import annotations

import json
import os
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from brief import config
from brief.dedupe import display_dt
from brief.health import summarise_health
from brief.normalise import to_iso
from brief.store import Store, read_json

LONDON = ZoneInfo("Europe/London")
DAY_FIELDS = ["id", "desk", "also_desks", "title", "url", "source_name", "publisher", "via", "published_at",
              "first_seen_at", "abstract", "summary", "summary_model", "summary_basis", "topics", "jurisdictions",
              "score", "pick", "paywalled", "revision", "updated_seen_at"]


def dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def new_7d(h: dict | None) -> int:
    by_day = (h or {}).get("new_by_day") or {}
    return sum(v for _, v in sorted(by_day.items())[-7:])


def london_date(item: dict) -> str:
    return display_dt(item).astimezone(LONDON).date().isoformat()


def build(out: Path, base: Path | None = None, now: datetime | None = None) -> dict:
    base = base or config.root()
    now = now or datetime.now(timezone.utc)
    settings = config.load_settings(base)
    topics = config.load_topics(base)
    sources_all = config.load_sources(base, include_disabled=True)
    by_id = config.source_map(sources_all)
    store = Store(base)
    health = summarise_health(base)
    backfill = read_json(base / "state" / "backfill.json", {})

    # clusters: leader is the best priority, then the earliest first_seen_at
    groups: dict[str, list[dict]] = defaultdict(list)
    for it in store.items.values():
        if it.get("cluster_id"):
            groups[it["cluster_id"]].append(it)
    also: dict[str, list[dict]] = {}
    hidden: set[str] = set()
    for members in groups.values():
        members.sort(key=lambda m: (by_id.get(m["source_id"], {}).get("priority", 2), m["first_seen_at"], m["id"]))
        leader, rest = members[0], members[1:]
        also[leader["id"]] = [{"source_name": m.get("publisher") or m["source_name"], "url": m["url"]} for m in rest]
        hidden.update(m["id"] for m in rest)

    days: dict[str, list[dict]] = defaultdict(list)
    months: dict[str, list[list]] = defaultdict(list)
    for it in store.items.values():
        if it["id"] in hidden:
            continue
        d = london_date(it)
        row = {k: it.get(k) for k in DAY_FIELDS}
        row["also"] = also.get(it["id"], [])
        row["_sort"] = to_iso(display_dt(it))
        days[d].append(row)
        months[d[:7]].append([it["id"], d, it["desk"], it["title"], row["publisher"] or it["source_name"],
                              it["url"], ",".join(it.get("topics", [])), 1 if it.get("pick") else 0])

    site = settings["site"]
    keep_days = sorted(days, reverse=True)[: site["days_on_site"]]
    keep_months = sorted(months, reverse=True)[: site["archive_months"]]

    if out.exists():
        shutil.rmtree(out)
    (out / "data" / "days").mkdir(parents=True)
    (out / "data" / "search").mkdir(parents=True)
    for f in sorted((base / "site").iterdir()):
        if f.is_file():
            shutil.copy2(f, out / f.name)
    sw = out / "sw.js"
    if sw.exists():
        sw.write_text(sw.read_text(encoding="utf-8").replace("__BUILD__", to_iso(now).replace(":", "")), encoding="utf-8")
    (out / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")

    day_index = []
    for d in keep_days:
        rows = sorted(days[d], key=lambda r: (r["_sort"], r["id"]), reverse=True)
        for r in rows:
            del r["_sort"]
        (out / "data" / "days" / f"{d}.json").write_text(dump(rows), encoding="utf-8")
        day_index.append({"date": d, "ip": sum(1 for r in rows if r["desk"] == "ip"),
                          "media": sum(1 for r in rows if r["desk"] == "media"),
                          "picks": sum(1 for r in rows if r["pick"])})
    for m in keep_months:
        rows = sorted(months[m], key=lambda r: (r[1], r[0]), reverse=True)
        (out / "data" / "search" / f"{m}.json").write_text(dump(rows), encoding="utf-8")

    status_by_id = {r["id"]: r["status"] for r in health["rows"]}
    hstate = read_json(base / "state" / "health.json", {})
    meta = {
        "generated_at": to_iso(now),
        "title": site["title"],
        "subtitle": site["subtitle"],
        "default_desk": site.get("default_desk", "ip"),
        "desks": {d: {"label": v["label"], "accent": v["accent"],
                      "topics": {t: tv["label"] for t, tv in v["topics"].items()}}
                  for d, v in topics["desks"].items()},
        "days": day_index,
        "months": keep_months,
        "sources": [{"id": s["id"], "name": s["name"], "desk": s["desk"], "homepage": s.get("homepage"),
                     "priority": s.get("priority", 2), "status": status_by_id.get(s["id"], "ok"),
                     "last_ok_at": hstate.get(s["id"], {}).get("last_ok_at"),
                     "new_7d": new_7d(hstate.get(s["id"]))}
                    for s in sources_all],
        "health": {"status": health["status"], "ok": health["ok"], "failing": len(health["failing"]),
                   "empty": len(health["empty"])},
        "summary_label": "AI summary. Check the source before you rely on it.",
        "licence_notes": sorted({s["licence_note"] for s in sources_all if s.get("enabled", True) and s.get("licence_note")}),
        "version": (os.environ.get("GITHUB_SHA") or "local")[:7],
        "backfill_until": backfill.get("last_backfill_finished_at"),
    }
    (out / "data" / "meta.json").write_text(dump(meta), encoding="utf-8")
    return {"days": len(keep_days), "months": len(keep_months), "items": sum(len(days[d]) for d in keep_days),
            "hidden_in_clusters": len(hidden)}
