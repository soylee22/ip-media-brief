"""JSON Lines item store and state files (SPEC 12)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def dumps_item(item: dict) -> str:
    return json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


class DuplicateIdError(Exception):
    pass


class Store:
    def __init__(self, base: Path):
        self.dir = base / "data" / "items"
        self.items: dict[str, dict] = {}
        self.month_of: dict[str, str] = {}
        self.dirty: set[str] = set()
        self._load()

    def _load(self) -> None:
        if not self.dir.exists():
            return
        for path in sorted(self.dir.glob("*.jsonl")):
            month = path.stem
            with path.open(encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    line = line.strip()
                    if not line:
                        continue
                    item = json.loads(line)
                    if item["id"] in self.items:
                        raise DuplicateIdError(f"{path.name}:{n}: duplicate id {item['id']}")
                    self.items[item["id"]] = item
                    self.month_of[item["id"]] = month

    def add(self, item: dict) -> None:
        month = item["first_seen_at"][:7]
        self.items[item["id"]] = item
        self.month_of[item["id"]] = month
        self.dirty.add(month)

    def touch(self, item_id: str) -> None:
        self.dirty.add(self.month_of[item_id])

    def month_text(self, month: str) -> str:
        rows = [it for iid, it in self.items.items() if self.month_of[iid] == month]
        rows.sort(key=lambda it: (it["first_seen_at"], it["id"]))
        return "".join(dumps_item(it) + "\n" for it in rows)

    def save(self) -> list[str]:
        written = []
        self.dir.mkdir(parents=True, exist_ok=True)
        for month in sorted(self.dirty):
            path = self.dir / f"{month}.jsonl"
            text = self.month_text(month)
            if path.exists() and path.read_text(encoding="utf-8") == text:
                continue
            tmp = path.with_suffix(".jsonl.tmp")
            tmp.write_text(text, encoding="utf-8", newline="\n")
            tmp.replace(path)
            written.append(path.name)
        self.dirty.clear()
        return written
