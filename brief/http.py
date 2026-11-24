"""HTTP rules (SPEC 8): honest user agent, retries, one request per host at a time, conditional GET."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ACCEPT = "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/html;q=0.8, */*;q=0.5"


class FetchError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class Fetcher:
    def __init__(self, settings: dict, cache_path: Path | None = None, client: httpx.Client | None = None):
        c = settings["collect"]
        self.user_agent = c["user_agent"]
        self.timeout = c["timeout_seconds"]
        self.retries = c["retries"]
        self.delay = c["per_host_delay_seconds"]
        self.client = client or httpx.Client(
            follow_redirects=True,
            timeout=self.timeout,
            headers={"User-Agent": self.user_agent, "Accept": ACCEPT},
        )
        self._host_locks: dict[str, threading.Lock] = {}
        self._host_last: dict[str, float] = {}
        self._guard = threading.Lock()
        self.cache_path = cache_path
        self.cache: dict[str, dict] = {}
        if cache_path and cache_path.exists():
            try:
                self.cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.cache = {}

    def _lock_for(self, host: str) -> threading.Lock:
        with self._guard:
            return self._host_locks.setdefault(host, threading.Lock())

    def get(self, url: str, conditional: bool = False, accept: str | None = None) -> httpx.Response | None:
        """Return the response, or None for 304 Not Modified. Raise FetchError on failure."""
        host = urlsplit(url).netloc.lower()
        headers = {}
        if accept:
            headers["Accept"] = accept
        if conditional and url in self.cache:
            entry = self.cache[url]
            if entry.get("etag"):
                headers["If-None-Match"] = entry["etag"]
            if entry.get("last_modified"):
                headers["If-Modified-Since"] = entry["last_modified"]
        waits = [3, 9][: self.retries]
        last_error = "unknown error"
        with self._lock_for(host):
            for attempt in range(len(waits) + 1):
                gap = time.monotonic() - self._host_last.get(host, 0.0)
                if gap < self.delay:
                    time.sleep(self.delay - gap)
                try:
                    resp = self.client.get(url, headers=headers)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last_error = f"{type(exc).__name__}: {exc}"[:200]
                    self._host_last[host] = time.monotonic()
                    if attempt < len(waits):
                        time.sleep(waits[attempt])
                        continue
                    raise FetchError(last_error) from exc
                self._host_last[host] = time.monotonic()
                if resp.status_code == 304:
                    return None
                if resp.status_code >= 500 and attempt < len(waits):
                    last_error = f"HTTP {resp.status_code}"
                    time.sleep(waits[attempt])
                    continue
                if resp.status_code >= 400:
                    raise FetchError(f"HTTP {resp.status_code}", resp.status_code)
                if conditional:
                    etag = resp.headers.get("ETag")
                    lm = resp.headers.get("Last-Modified")
                    if etag or lm:
                        self.cache[url] = {"etag": etag, "last_modified": lm}
                return resp
        raise FetchError(last_error)

    def save_cache(self) -> None:
        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.cache_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.cache, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            tmp.replace(self.cache_path)

    def close(self) -> None:
        self.client.close()
