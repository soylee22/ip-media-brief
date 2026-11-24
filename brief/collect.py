"""The collect command: SPEC 7 to 10 and 17."""
from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from rapidfuzz import fuzz

from brief import config
from brief.adapters import get_adapter
from brief.adapters.gnews import build_url as gnews_url
from brief.classify import Classifier
from brief.dedupe import ClusterIndex
from brief.http import FetchError, Fetcher
from brief.models import FetchContext, SourceError
from brief.normalise import (canonical_url, clean_abstract, clean_text, clean_title, fcl_abstract,
                             fingerprint, sane_published, sha16, to_iso)
from brief.robots import Robots
from brief.store import Store, read_json, write_json

log = logging.getLogger("brief.collect")
SUMMARY_FIELDS = ("summary", "summary_provider", "summary_model", "summary_basis", "summarised_at")


def host_of(src: dict) -> str:
    if src["adapter"] == "gnews":
        return urlsplit(gnews_url("x")).netloc
    return urlsplit(src["url"]).netloc.lower()


def fetch_all(sources: list[dict], ctx: FetchContext, workers: int) -> dict[str, object]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for s in sources:
        groups[host_of(s)].append(s)
    results: dict[str, object] = {}

    def run_group(group: list[dict]) -> None:
        for s in group:
            try:
                results[s["id"]] = get_adapter(s["adapter"])(s, ctx)
            except (SourceError, FetchError) as exc:
                results[s["id"]] = exc
            except Exception as exc:  # one broken adapter must not stop the run
                results[s["id"]] = SourceError(f"{type(exc).__name__}: {exc}")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(run_group, groups.values()))
    return results


def make_abstract(src: dict, e, title: str, max_chars: int) -> str:
    if src["adapter"] == "gnews":
        return ""
    if src["adapter"] == "fcl":
        return fcl_abstract(e.extra.get("court"), e.extra.get("citation"))
    return clean_abstract(e.description, e.content, title, max_chars)


def update_health(health: dict, src: dict, now_iso: str, error: str | None, status: int | None,
                  entries: int, new: int, today: str) -> None:
    h = health.setdefault(src["id"], {"consecutive_failures": 0, "consecutive_empty": 0, "new_by_day": {}})
    h["last_attempt_at"] = now_iso
    if error:
        h["consecutive_failures"] = h.get("consecutive_failures", 0) + 1
        h["last_error"] = error[:200]
        h["last_status"] = status
        return
    had_entries = (h.get("entries_last_run") or 0) > 0 or h.get("ever_had_entries", False)
    h["consecutive_failures"] = 0
    h["last_ok_at"] = now_iso
    h["last_status"] = 200
    h["last_error"] = None
    h["consecutive_empty"] = h.get("consecutive_empty", 0) + 1 if (entries == 0 and had_entries) else 0
    if entries:
        h["ever_had_entries"] = True
    h["entries_last_run"] = entries
    h["new_last_run"] = new
    by_day = h.setdefault("new_by_day", {})
    by_day[today] = by_day.get(today, 0) + new
    for d in sorted(by_day)[:-14]:
        del by_day[d]


def run(mode: str = "normal", days: int = 90, only: list[str] | None = None,
        base: Path | None = None, now: datetime | None = None, fetcher: Fetcher | None = None) -> dict:
    base = base or config.root()
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    now_iso = to_iso(now)
    settings = config.load_settings(base)
    sources = config.load_sources(base)
    if only:
        sources = [s for s in sources if s["id"] in set(only)]
    classifier = Classifier(config.load_topics(base))
    store = Store(base)
    c = settings["collect"]
    floor_days = days if mode == "backfill" else c["max_item_age_days"]
    age_floor = now - timedelta(days=floor_days)
    own_fetcher = fetcher is None
    fetcher = fetcher or Fetcher(settings, base / "state" / "http_cache.json")
    ctx = FetchContext(fetcher=fetcher, robots=Robots(fetcher, c["respect_robots_txt"]), mode=mode,
                       age_floor=age_floor,
                       max_pages=c["max_pages_backfill"] if mode == "backfill" else c["max_pages_normal"],
                       known_ids=set(store.items), settings=settings)
    results = fetch_all(sources, ctx, c["max_workers"])

    health = read_json(base / "state" / "health.json", {})
    cl = settings["cluster"]
    index = ClusterIndex(store.items, now, cl["title_similarity"], cl["window_days"], floor_days)
    by_id = config.source_map(config.load_sources(base, include_disabled=True))
    feed_text: dict[str, str] = read_json(base / "_work" / "feed_text.json", {})
    dropped: list[dict] = []
    report: dict[str, dict] = {}
    totals = {"ok": 0, "failing": 0, "entries": 0, "new": 0, "revised": 0, "dropped": 0}
    seen_run: set[str] = set()
    today = now.date().isoformat()

    def drop(src, title, rule):
        totals["dropped"] += 1
        if len(dropped) < 20:
            dropped.append({"source_id": src["id"], "title": title, "rule": rule})

    for src in sources:
        res = results.get(src["id"])
        if isinstance(res, Exception):
            totals["failing"] += 1
            status = getattr(res, "status", None)
            update_health(health, src, now_iso, str(res) or type(res).__name__, status, 0, 0, today)
            report[src["id"]] = {"status": "error", "error": str(res)[:200]}
            continue
        entries = res or []
        totals["ok"] += 1
        totals["entries"] += len(entries)
        candidates = []
        revised = 0
        for e in entries:
            title = clean_title(e.title)
            if len(title) < 3:
                continue
            try:
                canon = canonical_url(e.url)
            except ValueError:
                continue
            iid = sha16(canon)
            pub = sane_published(e.published, e.updated, now)
            if pub is not None and pub < age_floor:
                continue
            abstract = make_abstract(src, e, title, c["abstract_max_chars"])
            text = f"{title} {abstract}"
            if src.get("_include_re") and not any(rx.search(text) for rx in src["_include_re"]):
                drop(src, title, "include")
                continue
            match_title = f"{title} - {e.publisher}" if (src["adapter"] == "gnews" and e.publisher) else title
            rule = next((rx.pattern for rx in src.get("_exclude_re", []) if rx.search(match_title)), None)
            rule = rule or classifier.noise_rule(title)
            if rule:
                drop(src, title, rule)
                continue
            fp = fingerprint(title, abstract)
            if iid in store.items:
                it = store.items[iid]
                if it["fingerprint"] != fp and iid not in seen_run:
                    old_title = it["title"]
                    it.update(title=title, abstract=abstract, fingerprint=fp, revision=it["revision"] + 1,
                              updated_seen_at=now_iso)
                    if fuzz.token_set_ratio(old_title, title) < 80:
                        for f in SUMMARY_FIELDS:
                            it[f] = None
                        it["summary_attempts"] = 0
                    classifier.apply(it, by_id.get(it["source_id"]))
                    store.touch(iid)
                    revised += 1
                    seen_run.add(iid)
                continue
            if iid in seen_run:
                continue
            seen_run.add(iid)
            gn = src["adapter"] == "gnews"
            item = {
                "id": iid, "url": canon, "url_original": e.url if e.url != canon else None,
                "source_id": src["id"], "source_name": src["name"],
                "publisher": e.publisher if gn else None, "via": "Google News" if gn else None,
                "desk": src["desk"], "also_desks": [], "title": title, "abstract": abstract,
                "published_at": to_iso(pub), "first_seen_at": now_iso, "updated_seen_at": None,
                "revision": 1, "fingerprint": fp, "topics": [], "jurisdictions": [], "score": 0,
                "pick": False, "matched_terms": [], "cluster_id": None,
                "paywalled": bool(src.get("paywalled")), "summary": None, "summary_provider": None,
                "summary_model": None, "summary_basis": None, "summarised_at": None, "summary_attempts": 0,
            }
            text_for_summary = clean_text(e.content) or clean_text(e.description)
            candidates.append((pub or now, item, text_for_summary))
        candidates.sort(key=lambda t: t[0], reverse=True)
        new = 0
        cap = src.get("max_new_per_run", 30) * (10 if mode == "backfill" else 1)
        for _pub, item, text_for_summary in candidates[:cap]:
            other = index.match(item, store.items)
            members = [item["id"]]
            if other is not None:
                if index.is_gnews_duplicate(item, other):
                    drop(src, item["title"], "duplicate of a direct source")
                    continue
                members = index.join(item, other, store.items)
            classifier.apply(item, src, cluster_size=len(members))
            store.add(item)
            index.add_row(item)
            if len(members) > 1:
                for mid in members:
                    if mid != item["id"] and mid in store.items:
                        m = store.items[mid]
                        classifier.apply(m, by_id.get(m["source_id"]), cluster_size=len(members))
                        store.touch(mid)
            if text_for_summary and src["adapter"] != "fcl":
                feed_text[item["id"]] = text_for_summary
            new += 1
        totals["new"] += new
        totals["revised"] += revised
        update_health(health, src, now_iso, None, None, len(entries), new, today)
        report[src["id"]] = {"status": "ok", "entries": len(entries), "new": new, "revised": revised}

    store.save()
    fetcher.save_cache()
    if own_fetcher:
        fetcher.close()
    write_json(base / "state" / "health.json", health)
    write_json(base / "_work" / "feed_text.json", feed_text)
    finished = to_iso(datetime.now(timezone.utc))
    write_json(base / "state" / "run_report.json", {
        "started_at": now_iso, "finished_at": finished, "mode": mode, "totals": totals,
        "sources": report, "dropped": dropped,
    })
    if mode == "backfill":
        write_json(base / "state" / "backfill.json", {"last_backfill_finished_at": finished})
    return totals
