"""Command line (SPEC 18): python -m brief <command>."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator


def _ids(value: str | None) -> list[str] | None:
    ids = [v.strip() for v in (value or "").split(",") if v.strip()]
    return ids or None


def cmd_collect(a) -> int:
    from brief import collect
    t = collect.run(mode=a.mode, days=a.days, only=_ids(a.only))
    print(f"collect: {t['ok']} ok, {t['failing']} failing, {t['new']} new, {t['revised']} revised, {t['dropped']} dropped")
    return 0


def cmd_summarise(a) -> int:
    from brief import summarise
    r = summarise.run(a.provider, max_n=a.max)
    print(f"summarise ({r['provider']}): state {r['state']}, {r['summarised']} written, {r['failed']} failed, "
          f"{r['skipped']} without text, {r['remaining']} still eligible"
          + (f", needs_local={str(r['needs_local']).lower()}" if "needs_local" in r else ""))
    return 0


def cmd_validate(a) -> int:
    from brief import config
    from brief.store import Store
    base = config.root()
    errors = 0
    try:
        config.load_settings(base)
        sources = config.load_sources(base, include_disabled=True)
        config.load_topics(base)
    except Exception as exc:  # report any config problem as one line
        print(f"validate: config error: {exc}")
        return 1
    schema = json.loads((base / "schemas" / "item.schema.json").read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    try:
        store = Store(base)
    except Exception as exc:
        print(f"validate: data error: {exc}")
        return 1
    for it in store.items.values():
        for err in validator.iter_errors(it):
            errors += 1
            if errors <= 10:
                print(f"validate: item {it.get('id')}: {list(err.path)} {err.message[:120]}")
    for p in sorted((base / "state").glob("*.json")):
        try:
            json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors += 1
            print(f"validate: {p.name}: {exc}")
    print(f"validate: {len(sources)} sources, {len(store.items)} items, {errors} errors")
    return 1 if errors else 0


def cmd_build(a) -> int:
    from brief import build_site
    r = build_site.build(Path(a.out))
    print(f"build: {r['items']} items over {r['days']} days, {r['months']} search months, "
          f"{r['hidden_in_clusters']} grouped under other stories")
    return 0


def cmd_health(a) -> int:
    from brief import health
    try:
        s = health.run(issue_file=a.issue_file, github_output=a.github_output)
        print(f"health: {s['status']}, {s['ok']} ok, {len(s['failing'])} failing, {len(s['empty'])} empty")
    except Exception as exc:  # the health command never fails the run (SPEC 16.8)
        print(f"health: could not compute: {exc}")
        if a.github_output:
            with open(a.github_output, "a", encoding="utf-8") as fh:
                fh.write("status=amber\n")
    return 0


def cmd_probe(a) -> int:
    from brief import probe
    rows = probe.run(only=_ids(a.only), report=a.report)
    ok = sum(1 for r in rows if r["ok"])
    print(f"probe: {ok} of {len(rows)} sources OK")
    for r in rows:
        if not r["ok"]:
            print(f"  FAIL {r['id']}: {r['error']}")
    return 0


def cmd_stats(a) -> int:
    from brief import config
    from brief.store import Store
    store = Store(config.root())
    items = list(store.items.values())
    print(f"stats: {len(items)} items")
    for label, key in (("desk", "desk"), ("source", "source_id")):
        print(f"  by {label}: " + ", ".join(f"{k} {v}" for k, v in Counter(i[key] for i in items).most_common(15)))
    print("  by month: " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(store.month_of.values()).items())))
    print(f"  with summary: {sum(1 for i in items if i.get('summary'))}, picks: {sum(1 for i in items if i.get('pick'))}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=os.environ.get("BRIEF_LOG", "WARNING"), format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="brief")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--mode", choices=["normal", "backfill"], default="normal")
    c.add_argument("--days", type=int, default=90)
    c.add_argument("--only", default="")
    c.set_defaults(func=cmd_collect)
    s = sub.add_parser("summarise")
    s.add_argument("--provider", choices=["gemini", "ollama"], required=True)
    s.add_argument("--max", type=int, default=None)
    s.set_defaults(func=cmd_summarise)
    sub.add_parser("validate").set_defaults(func=cmd_validate)
    b = sub.add_parser("build")
    b.add_argument("--out", default="_site")
    b.set_defaults(func=cmd_build)
    h = sub.add_parser("health")
    h.add_argument("--issue-file", default=None)
    h.add_argument("--github-output", default=None)
    h.set_defaults(func=cmd_health)
    pr = sub.add_parser("probe")
    pr.add_argument("--only", default="")
    pr.add_argument("--report", default=None)
    pr.set_defaults(func=cmd_probe)
    sub.add_parser("stats").set_defaults(func=cmd_stats)
    a = p.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
