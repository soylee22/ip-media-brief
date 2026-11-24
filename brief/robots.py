"""robots.txt checks for HTML pages and article fetches (SPEC 8.11)."""
from __future__ import annotations

import threading
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from brief.http import FetchError, Fetcher


class Robots:
    def __init__(self, fetcher: Fetcher, enabled: bool = True):
        self.fetcher = fetcher
        self.enabled = enabled
        self._cache: dict[str, RobotFileParser | None] = {}
        self._lock = threading.Lock()

    def allowed(self, url: str) -> bool:
        if not self.enabled:
            return True
        parts = urlsplit(url)
        base = f"{parts.scheme}://{parts.netloc}"
        with self._lock:
            known = base in self._cache
        if not known:
            parser: RobotFileParser | None = RobotFileParser()
            try:
                resp = self.fetcher.get(base + "/robots.txt", accept="text/plain")
                parser.parse((resp.text if resp is not None else "").splitlines())
            except FetchError as exc:
                if exc.status in (401, 403):
                    parser.parse(["User-agent: *", "Disallow: /"])
                else:
                    parser = None  # no robots.txt means everything is allowed
            with self._lock:
                self._cache[base] = parser
        parser = self._cache[base]
        if parser is None:
            return True
        return parser.can_fetch(self.fetcher.user_agent, url)
