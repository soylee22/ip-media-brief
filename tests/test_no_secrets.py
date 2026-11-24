"""No API key may ever sit in the repository (SPEC 19, A8)."""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
KEY = re.compile(r"AIza[0-9A-Za-z_-]{35}")
SKIP = {".git", ".venv", "_site", "_work", "_out", "__pycache__", ".pytest_cache"}


def test_no_google_api_key_in_repository():
    hits = []
    for p in REPO.rglob("*"):
        if p.is_file() and not (SKIP & set(p.relative_to(REPO).parts)) and p.stat().st_size < 50_000_000:
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if KEY.search(text):
                hits.append(str(p.relative_to(REPO)))
    assert not hits, f"API key pattern found in: {hits}"
