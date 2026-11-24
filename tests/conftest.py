"""Shared fixtures. Tests make no network requests (SPEC 19)."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from brief.http import FetchError

REPO = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)


def rss(items: list[tuple[str, str, str, str]]) -> bytes:
    """items: (title, link, description, rfc822 date)."""
    body = "".join(f"<item><title>{t}</title><link>{l}</link><description>{d}</description><pubDate>{p}</pubDate></item>"
                   for t, l, d, p in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>{body}</channel></rss>'.encode()


class FakeResponse:
    def __init__(self, content: bytes, url: str, status: int = 200):
        self.content = content
        self.text = content.decode("utf-8", "replace")
        self.url = url
        self.status_code = status
        self.headers = {}

    def json(self):
        return json.loads(self.text)


class FakeFetcher:
    user_agent = "test-agent"

    def __init__(self, pages: dict[str, bytes]):
        self.pages = pages
        self.calls: list[str] = []

    def get(self, url, conditional=False, accept=None):
        self.calls.append(url)
        for key, content in self.pages.items():
            if url == key or url.startswith(key + "&") or url.startswith(key + "?"):
                if isinstance(content, Exception):
                    raise content
                return FakeResponse(content, url)
        raise FetchError("HTTP 404", 404)

    def save_cache(self):
        pass

    def close(self):
        pass


@pytest.fixture
def base(tmp_path: Path, monkeypatch) -> Path:
    for d in ("config", "schemas", "prompts", "site"):
        shutil.copytree(REPO / d, tmp_path / d)
    (tmp_path / "data" / "items").mkdir(parents=True)
    (tmp_path / "state").mkdir()
    monkeypatch.setenv("BRIEF_ROOT", str(tmp_path))
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    return tmp_path


def write_sources(base: Path, sources_yaml: str) -> None:
    (base / "config" / "sources.yaml").write_text(
        "defaults:\n  enabled: true\n  priority: 2\n  paging: none\n  paywalled: false\n  fetch_article: true\n"
        "  max_new_per_run: 30\n  include: []\n  exclude: []\nsources:\n" + sources_yaml, encoding="utf-8")
