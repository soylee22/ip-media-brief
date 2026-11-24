"""Shared data types."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class SourceError(Exception):
    """The whole source failed. One bad entry never raises this."""


@dataclass
class Entry:
    url: str
    title: str
    description: str | None = None
    content: str | None = None
    published: datetime | None = None
    updated: datetime | None = None
    publisher: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchContext:
    fetcher: Any
    robots: Any
    mode: str
    age_floor: datetime
    max_pages: int
    known_ids: set[str]
    settings: dict[str, Any]
