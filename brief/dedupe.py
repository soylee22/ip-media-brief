"""Clusters of near-identical headlines from different sources (SPEC 10.2)."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from rapidfuzz import fuzz

from brief.normalise import from_iso, norm_for_compare


def display_dt(item: dict) -> datetime:
    return from_iso(item.get("published_at")) or from_iso(item["first_seen_at"])


def _publisher_key(text: str | None) -> str:
    return norm_for_compare(text or "")


class ClusterIndex:
    def __init__(self, items: dict[str, dict], now: datetime, threshold: int, window_days: int, lookback_days: int):
        self.threshold = threshold
        self.window = timedelta(days=window_days)
        floor = now - timedelta(days=lookback_days + window_days)
        self.rows: list[tuple[str, str, datetime]] = []
        self.members: dict[str, list[str]] = defaultdict(list)
        for iid, it in items.items():
            if it.get("cluster_id"):
                self.members[it["cluster_id"]].append(iid)
            dt = display_dt(it)
            if dt >= floor:
                self.rows.append((iid, norm_for_compare(it["title"]), dt))

    def match(self, item: dict, items: dict[str, dict]) -> dict | None:
        title = norm_for_compare(item["title"])
        dt = display_dt(item)
        best, best_score = None, 0.0
        for iid, other_title, other_dt in self.rows:
            if iid == item["id"] or abs(other_dt - dt) > self.window:
                continue
            score = fuzz.token_set_ratio(title, other_title)
            if score >= self.threshold and score > best_score:
                best, best_score = items[iid], score
        return best

    def is_gnews_duplicate(self, item: dict, other: dict) -> bool:
        """A Google News item from the same publisher as a direct item (SPEC 10.2 rule 4)."""
        if item.get("via") != "Google News" or other.get("via"):
            return False
        pub = _publisher_key(item.get("publisher"))
        name = _publisher_key(other.get("source_name"))
        return bool(pub) and (pub in name or name in pub)

    def join(self, item: dict, other: dict, items: dict[str, dict]) -> list[str]:
        key = other.get("cluster_id") or other["id"]
        if not other.get("cluster_id"):
            other["cluster_id"] = key
            self.members[key].append(other["id"])
        item["cluster_id"] = key
        self.members[key].append(item["id"])
        return list(dict.fromkeys(self.members[key]))

    def add_row(self, item: dict) -> None:
        self.rows.append((item["id"], norm_for_compare(item["title"]), display_dt(item)))
