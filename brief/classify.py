"""Topics, cross-desk, jurisdictions, relevance and picks (SPEC 10.4 to 10.8)."""
from __future__ import annotations


class Classifier:
    def __init__(self, topics_cfg: dict):
        self.cfg = topics_cfg
        rel = topics_cfg["relevance"]
        self.priority_points = {int(k): v for k, v in rel["source_priority_points"].items()}
        self.cov_each = rel["coverage_points_per_extra_source"]
        self.cov_max = rel["coverage_points_max"]
        self.cap = rel["score_cap"]
        self.pick_threshold = rel["pick_threshold"]

    def noise_rule(self, title: str) -> str | None:
        for pattern, rx in self.cfg["_noise_re"]:
            if rx.search(title):
                return pattern
        return None

    def topics(self, desk: str, title: str, abstract: str, hint: list[str] | None) -> list[str]:
        points: dict[str, int] = {}
        for tid, topic in self.cfg["desks"][desk]["topics"].items():
            p = 0
            for rx in topic["_re"]:
                if rx.search(title):
                    p += 2
                if abstract and rx.search(abstract):
                    p += 1
            if p:
                points[tid] = p
        ranked = sorted(points, key=lambda t: (-points[t], t))[:4]
        if not ranked and hint:
            valid = self.cfg["desks"][desk]["topics"]
            ranked = [t for t in hint if t in valid][:4]
        return ranked

    def also_desks(self, desk: str, title: str) -> list[str]:
        out = []
        for other, tids in self.cfg.get("cross_desk_topics", {}).items():
            if other == desk:
                continue
            topics = self.cfg["desks"][other]["topics"]
            if any(rx.search(title) for tid in tids if tid in topics for rx in topics[tid]["_re"]):
                out.append(other)
        return out

    def jurisdictions(self, desk: str, title: str, abstract: str, defaults: list[str] | None) -> list[str]:
        found = list(defaults or [])
        text = f"{title} {abstract}"
        for j, rxs in self.cfg["_jur_re"].items():
            if j not in found and any(rx.search(text) for rx in rxs):
                found.append(j)
        if not found and desk == "ip":
            found = ["global"]
        order = ["uk", "eu", "us", "cn", "global"]
        return sorted(set(found), key=order.index)

    def score(self, title: str, abstract: str, priority: int, cluster_size: int = 1) -> tuple[int, bool, list[str]]:
        total = self.priority_points.get(int(priority), 0)
        matched: list[str] = []
        for _pattern, rx, weight in self.cfg["_rel_re"]:
            m = rx.search(title)
            if m:
                total += weight
            else:
                m = rx.search(abstract) if abstract else None
                if m:
                    total += weight // 2
            if m:
                word = m.group(0).strip()
                if word and word.lower() not in {w.lower() for w in matched}:
                    matched.append(word)
        total += min(self.cov_max, self.cov_each * max(0, cluster_size - 1))
        total = min(total, self.cap)
        return total, total >= self.pick_threshold, matched[:8]

    def apply(self, item: dict, source: dict | None, cluster_size: int = 1) -> None:
        source = source or {}
        desk = item["desk"]
        item["topics"] = self.topics(desk, item["title"], item["abstract"], source.get("topics_hint"))
        item["also_desks"] = self.also_desks(desk, item["title"])
        item["jurisdictions"] = self.jurisdictions(desk, item["title"], item["abstract"], source.get("jurisdictions"))
        score, pick, matched = self.score(item["title"], item["abstract"], source.get("priority", 2), cluster_size)
        item["score"], item["pick"], item["matched_terms"] = score, pick, matched
