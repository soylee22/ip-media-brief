"""URL, title, abstract, date and fingerprint rules (SPEC 9)."""
from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

DROP_PARAMS = {
    "fbclid", "gclid", "dclid", "mc_cid", "mc_eid", "ref", "ref_src", "cmpid", "CMP", "ito",
    "at_medium", "at_campaign", "ocid", "s_cid", "sr_share", "taid", "rss", "src", "feed", "share",
}

BOILERPLATE = [
    re.compile(r"The post .* appeared first on .*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"(Continue|Read) (reading|more).*$", re.IGNORECASE | re.DOTALL),
    re.compile(r"\[(…|\.\.\.)\]", re.IGNORECASE),
    re.compile(r"^By [A-Z][\w.'-]+( [A-Z][\w.'-]+){0,3}\s*[,|:-]?\s*"),
]

CITATION_RE = re.compile(r"\[\d{4}\] (UKSC|UKPC|EWCA (Civ|Crim)|EWHC|UKUT|UKFTT|EAT)\s*\d+(\s*\([A-Za-z]+\))?")
QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"
    if parts.username:
        host = f"{parts.username}@{host}"
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if not k.startswith("utm_") and k not in DROP_PARAMS]
    query.sort(key=lambda kv: kv[0])
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunsplit((scheme, host, path, urlencode(query), ""))


def sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def item_id(url: str) -> str:
    return sha16(canonical_url(url))


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def strip_html(text: str | None) -> str:
    if not text:
        return ""
    if "<" in text and ">" in text:
        text = BeautifulSoup(text, "lxml").get_text(" ")
    return _collapse(html.unescape(text))


def clean_title(raw: str | None, max_len: int = 300) -> str:
    title = strip_html(raw).translate(QUOTES)
    if len(title) > max_len:
        cut = title[:max_len].rsplit(" ", 1)[0]
        title = cut or title[:max_len]
    return title


def clean_text(raw: str | None) -> str:
    """Steps 1 and 2 of SPEC 9.3, used for summary source text too."""
    return strip_html(raw).translate(QUOTES)


def clean_abstract(description: str | None, content: str | None, title: str, max_chars: int = 240) -> str:
    text = clean_text(description) or clean_text(content)
    for pattern in BOILERPLATE:
        text = pattern.sub("", text).strip()
    text = _collapse(text)
    if title and text.lower().startswith(title.lower()):
        text = text[len(title):].lstrip(" .:-|")
    if len(text) > max_chars:
        m = re.search(r"(?<=[.!?])\s", text[60:])
        if m and 60 + m.start() <= max_chars:
            text = text[: 60 + m.start()].strip()
    if len(text) > max_chars:
        cut = text[: max_chars - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
        text = cut + "…"
    return text


def fcl_abstract(court: str | None, citation: str | None) -> str:
    parts = []
    if court:
        parts.append(f"{court} judgment.")
    if citation:
        parts.append(f"{citation}.")
    return " ".join(parts)[:240]


def find_citation(*texts: str | None) -> str | None:
    for t in texts:
        if t:
            m = CITATION_RE.search(t)
            if m:
                return m.group(0)
    return None


def to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def from_iso(text: str | None) -> datetime | None:
    if not text:
        return None
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def sane_published(published: datetime | None, updated: datetime | None, now: datetime) -> datetime | None:
    dt = published or updated
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt > now + timedelta(days=1):
        return None
    return dt


def fingerprint(title: str, abstract: str) -> str:
    return sha16(f"{title}\n{abstract}")


def norm_for_compare(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[^\w\s]", " ", t)
    return _collapse(t)
