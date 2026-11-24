"""Load and check the YAML configuration (SPEC 6, 7.1 and 10.4)."""
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

REQUIRED_SETTINGS = ["site", "collect", "cluster", "summarise", "health"]


class ConfigError(Exception):
    pass


def root() -> Path:
    """Repository root. BRIEF_ROOT overrides it for tests."""
    env = os.environ.get("BRIEF_ROOT")
    return Path(env).resolve() if env else Path(__file__).resolve().parents[1]


def _plain(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _plain(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_plain(v) for v in obj]
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return obj


def _load_yaml(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as fh:
            return _plain(yaml.safe_load(fh))
    except FileNotFoundError as exc:
        raise ConfigError(f"Missing file: {path}") from exc


def load_settings(base: Path | None = None) -> dict:
    base = base or root()
    data = _load_yaml(base / "config" / "settings.yaml")
    for key in REQUIRED_SETTINGS:
        if key not in data:
            raise ConfigError(f"settings.yaml: missing key '{key}'")
    ollama = data["summarise"].get("ollama", {})
    if "models_dir" in ollama:
        ollama["models_dir"] = os.path.expanduser(ollama["models_dir"])
    return data


def compile_pattern(pattern: str) -> re.Pattern:
    """A 'cs:' prefix means match with case. Otherwise ignore case (SPEC 10.4)."""
    if pattern.startswith("cs:"):
        return re.compile(pattern[3:])
    return re.compile(pattern, re.IGNORECASE)


def load_sources(base: Path | None = None, include_disabled: bool = False) -> list[dict]:
    base = base or root()
    data = _load_yaml(base / "config" / "sources.yaml")
    schema = json.loads((base / "schemas" / "sources.schema.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        raise ConfigError(f"sources.yaml: {list(first.path)}: {first.message}")
    defaults = data.get("defaults", {})
    seen: set[str] = set()
    out = []
    for raw in data["sources"]:
        src = {**defaults, **raw}
        if src["id"] in seen:
            raise ConfigError(f"sources.yaml: duplicate id '{src['id']}'")
        seen.add(src["id"])
        if src["adapter"] == "gnews":
            src["fetch_article"] = False
        for key in ("include", "exclude"):
            try:
                src[f"_{key}_re"] = [re.compile(p) for p in src.get(key, [])]
            except re.error as exc:
                raise ConfigError(f"sources.yaml: {src['id']} {key} pattern: {exc}") from exc
        if src.get("enabled", True) or include_disabled:
            out.append(src)
    return out


def load_topics(base: Path | None = None) -> dict:
    base = base or root()
    data = _load_yaml(base / "config" / "topics.yaml")

    def comp(p: str, where: str) -> re.Pattern:
        try:
            return compile_pattern(p)
        except re.error as exc:
            raise ConfigError(f"topics.yaml: {where}: '{p}': {exc}") from exc

    for desk_id, desk in data["desks"].items():
        for tid, topic in desk["topics"].items():
            topic["_re"] = [comp(p, f"{desk_id}.{tid}") for p in topic["patterns"]]
    data["_jur_re"] = {j: [comp(p, f"jurisdictions.{j}") for p in pats] for j, pats in data["jurisdictions"].items()}
    data["_rel_re"] = [(p, comp(p, "relevance.terms"), w) for p, w in data["relevance"]["terms"].items()]
    data["_noise_re"] = [(p, comp(p, "noise.title_exclude")) for p in data["noise"]["title_exclude"]]
    return data


def source_map(sources: list[dict]) -> dict[str, dict]:
    return {s["id"]: s for s in sources}
