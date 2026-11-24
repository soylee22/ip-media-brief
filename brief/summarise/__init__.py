"""The summarise command (SPEC 11). Article text stays in memory. It is never stored."""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import trafilatura

from brief import config
from brief.dedupe import display_dt
from brief.http import FetchError, Fetcher
from brief.normalise import to_iso
from brief.robots import Robots
from brief.store import Store, read_json, write_json

FIRST_PERSON = re.compile(r"\b(I|We|we|Our|our|My|my)\b")
BANNED = ("the article", "this article", "the author", "as an ai")
ENTITY = re.compile(r"\b([A-Z][\w&'-]+|\d[\d,.%]*)\b")
ENTITY_STOP = {"The", "A", "An", "This", "It", "UK", "EU", "US"}
RETRY_LINE = "Your previous answer broke a rule. Follow every rule exactly."


def load_prompt(base: Path) -> tuple[str, str]:
    text = (base / "prompts" / "summary.md").read_text(encoding="utf-8")
    blocks = re.findall(r"## (SYSTEM|USER)\s+```\n(.*?)\n```", text, re.DOTALL)
    found = dict(blocks)
    return found["SYSTEM"], found["USER"]


def cut_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    clipped = " ".join(words[:max_words])
    end = max(clipped.rfind(". "), clipped.rfind("? "), clipped.rfind("! "))
    return clipped[: end + 1] if end > len(clipped) // 2 else clipped


def validate(summary: str, source: str, s: dict) -> str | None:
    """Return None when the summary passes, else the broken rule."""
    words = summary.split()
    if not (s["min_words"] <= len(words) <= s["max_words"]):
        return f"length {len(words)} words"
    low = summary.lower()
    if "http" in low or "www." in low or "\n" in summary or summary.lstrip()[:1] in ("#", "*"):
        return "format"
    if FIRST_PERSON.search(summary):
        return "first person"
    if any(b in low for b in BANNED):
        return "banned phrase"
    tokens = []
    for sentence in re.split(r"(?<=[.!?])\s+", summary):
        found = ENTITY.findall(sentence)
        first = sentence.split()[0].strip("\"'(") if sentence.split() else ""
        tokens += [t for t in found if t not in ENTITY_STOP and t != first]
    if tokens:
        src = source.lower()
        hits = sum(1 for t in tokens if t.lower().rstrip(".,%") in src)
        if hits / len(tokens) < s["entity_overlap_min"]:
            return f"entity check {hits}/{len(tokens)}"
    return None


def parse_answer(text: str | None) -> str | None:
    import json
    if text is None:
        return None
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?|\n?```$", "", text).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    value = data.get("summary") if isinstance(data, dict) else None
    return value.strip() if isinstance(value, str) else None


def eligible(store: Store, by_id: dict, now: datetime, s: dict) -> list[dict]:
    floor = now - timedelta(days=s["max_item_age_days"])
    rows = []
    for it in store.items.values():
        src = by_id.get(it["source_id"], {})
        if it.get("summary") or it.get("summary_attempts", 0) >= 2 or src.get("adapter") == "fcl":
            continue
        if display_dt(it) < floor:
            continue
        rows.append(it)
    rows.sort(key=lambda it: it["first_seen_at"], reverse=True)
    rows.sort(key=lambda it: -it.get("score", 0))  # stable: score first, then newest
    return rows


def source_text(item: dict, src: dict, fetcher: Fetcher | None, robots: Robots | None,
                feed_text: dict, s: dict) -> tuple[str | None, str | None]:
    if fetcher and src.get("fetch_article") and not src.get("paywalled") and not item.get("via"):
        try:
            if robots is None or robots.allowed(item["url"]):
                resp = fetcher.get(item["url"], accept="text/html")
                if resp is not None:
                    text = trafilatura.extract(resp.text, include_comments=False, include_tables=False,
                                               favor_precision=True) or ""
                    if len(text) >= s["min_source_chars"]:
                        return cut_words(text, s["max_input_words"]), "article"
        except FetchError:
            pass
    text = feed_text.get(item["id"], "")
    if len(text) >= s["min_source_chars"]:
        return cut_words(text, s["max_input_words"]), "feed"
    return None, None


def write_outputs(path: str | None, lines: dict) -> None:
    if not path:
        return
    with open(path, "a", encoding="utf-8") as fh:
        for k, v in lines.items():
            fh.write(f"{k}={v}\n")


def run(provider: str, base: Path | None = None, now: datetime | None = None, max_n: int | None = None,
        client=None, fetcher: Fetcher | None = None, sleep=time.sleep) -> dict:
    from brief.summarise.gemini import Gemini
    from brief.summarise.ollama import Ollama

    base = base or config.root()
    now = now or datetime.now(timezone.utc)
    settings = config.load_settings(base)
    s = settings["summarise"]
    by_id = config.source_map(config.load_sources(base, include_disabled=True))
    store = Store(base)
    budget_path = base / "state" / "ai_budget.json"
    budget = read_json(budget_path, {})
    today = now.date().isoformat()
    if budget.get("date") != today:
        budget.update(date=today, gemini_calls=0, ollama_calls=0, gemini_state="ok")
    system, user_tpl = load_prompt(base)
    feed_text = read_json(base / "_work" / "feed_text.json", {})
    rows = eligible(store, by_id, now, s)
    providers = s.get("providers", [])
    result = {"provider": provider, "eligible": len(rows), "summarised": 0, "failed": 0, "skipped": 0, "state": "ok"}

    if provider not in providers:
        result["state"] = "disabled"
        p = None
    elif provider == "gemini":
        p = Gemini(s["gemini"], budget, client=client, sleep=sleep)
    else:
        p = Ollama(s["ollama"], budget, client=client)

    own_fetcher = fetcher is None and p is not None
    if own_fetcher:
        fetcher = Fetcher(settings)
    robots = Robots(fetcher, settings["collect"]["respect_robots_txt"]) if fetcher else None
    limit = max_n if max_n is not None else (s["gemini"]["per_run_cap"] if provider == "gemini" else s["ollama"]["per_run_cap"])
    started = time.monotonic()
    done = 0
    if p is not None:
        state = p.ready()
        result["state"] = state
        for it in rows:
            if state != "ok" or done >= limit:
                break
            if provider == "ollama" and time.monotonic() - started > s["ollama"]["max_run_minutes"] * 60:
                break
            src = by_id.get(it["source_id"], {})
            text, basis = source_text(it, src, fetcher, robots, feed_text, s)
            if not text:
                it["summary_attempts"] = 2
                store.touch(it["id"])
                result["skipped"] += 1
                continue
            user = (user_tpl.replace("{title}", it["title"])
                    .replace("{publisher_or_source_name}", it.get("publisher") or it["source_name"])
                    .replace("{published_date_or_unknown}", (it.get("published_at") or "unknown")[:10])
                    .replace("{source_text}", text))
            summary, reason, transient = None, None, False
            for attempt in range(2):
                answer, state = p.summarise(system, user if attempt == 0 else user + "\n\n" + RETRY_LINE)
                if state == "ok_skip":  # one network or server error: try this item on a later run
                    state, transient = "ok", True
                    break
                if state != "ok":
                    break
                parsed = parse_answer(answer)
                if parsed == "":
                    reason = "empty"
                    break
                if parsed is None:
                    reason = "not JSON"
                    continue
                reason = validate(parsed, text, s)
                if reason is None:
                    summary = parsed
                    break
            done += 1
            if summary:
                it.update(summary=summary, summary_provider=provider, summary_model=p.model_in_use(),
                          summary_basis=basis, summarised_at=to_iso(datetime.now(timezone.utc)))
                result["summarised"] += 1
            elif transient:
                result["failed"] += 1
            elif reason == "empty":
                it["summary_attempts"] = 2
                result["failed"] += 1
            elif state == "ok":
                it["summary_attempts"] = it.get("summary_attempts", 0) + 1
                result["failed"] += 1
            store.touch(it["id"])
        result["state"] = state if p is not None else result["state"]
        budget[f"{provider}_state"] = result["state"] if result["state"] != "cap" else "ok"
    if own_fetcher and fetcher:
        fetcher.close()
    store.save()
    write_json(budget_path, budget)

    remaining = len(eligible(store, by_id, now, s))
    if provider == "gemini":
        needs_local = remaining > 0 and "ollama" in providers and result["state"] in (
            "no_key", "exhausted", "rejected", "error", "disabled")
        o = s["ollama"]
        write_outputs(os.environ.get("GITHUB_OUTPUT"), {
            "needs_local": str(needs_local).lower(),
            "ollama_version": o["version"],
            "ollama_model": o["model"],
            "ollama_model_key": f"{o['model'].replace(':', '-')}-{o['version']}",
        })
        result["needs_local"] = needs_local
    result["remaining"] = remaining
    return result
