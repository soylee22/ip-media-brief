from datetime import datetime, timedelta, timezone

import pytest

from brief import config
from brief.normalise import (canonical_url, clean_abstract, clean_title, fcl_abstract, find_citation, item_id,
                             sane_published)
from tests.conftest import REPO, write_sources


def test_shipped_config_loads_and_compiles():
    settings = config.load_settings(REPO)
    sources = config.load_sources(REPO)
    topics = config.load_topics(REPO)
    assert settings["site"]["base_path"] == "/ip-media-brief/"
    assert len(sources) >= 80
    assert all(s["fetch_article"] is False for s in sources if s["adapter"] == "gnews")
    assert topics["_rel_re"]


def test_duplicate_source_id_fails(base):
    write_sources(base, "  - {id: a, name: A, desk: ip, adapter: rss, url: 'https://x.test/feed'}\n"
                        "  - {id: a, name: B, desk: ip, adapter: rss, url: 'https://y.test/feed'}\n")
    with pytest.raises(config.ConfigError):
        config.load_sources(base)


@pytest.mark.parametrize("raw, expected", [
    ("https://Example.com/a/?utm_source=x&b=2&a=1#top", "https://example.com/a?a=1&b=2"),
    ("https://example.com:443/", "https://example.com/"),
    ("http://example.com/news/item/", "http://example.com/news/item"),
])
def test_canonical_url(raw, expected):
    assert canonical_url(raw) == expected


def test_tracking_parameters_do_not_change_id():
    assert item_id("https://x.test/story?utm_medium=rss&fbclid=1") == item_id("https://x.test/story/")


def test_title_cleaning():
    assert clean_title("  <b>BBC&nbsp;wins</b>  ‘case’ ") == "BBC wins 'case'"


def test_abstract_rules():
    title = "Court rules on codec patents"
    desc = ("<p>Court rules on codec patents. The Patents Court ruled on Tuesday that the patent was valid. "
            "More detail follows in the judgment.</p><p>The post Court rules appeared first on Example Blog.</p>")
    out = clean_abstract(desc, None, title)
    assert "appeared first" not in out
    assert out.startswith("The Patents Court ruled")
    long = clean_abstract("word " * 200, None, "t")
    assert len(long) <= 240 and long.endswith("…")


def test_fcl_abstract_and_citation():
    cit = find_citation("Acme Ltd v Beta plc [2026] EWHC 1234 (Pat)")
    assert cit == "[2026] EWHC 1234 (Pat)"
    assert fcl_abstract("High Court (Patents Court)", cit) == "High Court (Patents Court) judgment. [2026] EWHC 1234 (Pat)."


def test_future_dates_become_null():
    now = datetime(2026, 11, 24, tzinfo=timezone.utc)
    assert sane_published(now + timedelta(days=3), None, now) is None
    assert sane_published(None, now, now) == now
