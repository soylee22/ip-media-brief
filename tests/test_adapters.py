from datetime import datetime, timezone

import pytest

from brief.adapters import page_url, parse_feed
from brief.adapters import embedded_json, gnews, govuk, html_list
from brief.models import FetchContext, SourceError
from tests.conftest import FakeFetcher, rss

ATOM = b"""<?xml version="1.0" encoding="utf-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>F</title>
<entry><title>Acme v Beta [2026] EWHC 9 (Pat)</title><link href="https://fcl.test/ewhc/pat/2026/9"/>
<id>https://fcl.test/ewhc/pat/2026/9</id><updated>2026-11-20T10:00:00Z</updated><published>2026-11-20T10:00:00Z</published>
<author><name>High Court (Patents Court)</name></author></entry></feed>"""


def ctx(fetcher, known=None, mode="normal"):
    return FetchContext(fetcher=fetcher, robots=type("R", (), {"allowed": lambda self, u: True})(), mode=mode,
                        age_floor=datetime(2026, 8, 1, tzinfo=timezone.utc), max_pages=3,
                        known_ids=known or set(), settings={})


def test_parse_rss_and_atom():
    entries = parse_feed(rss([("One", "https://a.test/1", "Desc", "Mon, 23 Nov 2026 10:00:00 GMT")]))
    assert entries[0].title == "One" and entries[0].published.year == 2026
    atom = parse_feed(ATOM)
    assert atom[0].extra["author"] == "High Court (Patents Court)"


def test_non_feed_raises():
    with pytest.raises(SourceError):
        parse_feed(b"<html><body>Not a feed</body></html>")


def test_gnews_strips_publisher():
    assert gnews.strip_publisher("Netflix carries CBeebies - Broadcast", "Broadcast") == "Netflix carries CBeebies"
    assert "q=site%3Abroadcastnow.co.uk" in gnews.build_url("site:broadcastnow.co.uk")


@pytest.mark.parametrize("style, n, backfill, expected", [
    ("wordpress", 1, False, "https://w.test/feed/"),
    ("wordpress", 3, False, "https://w.test/feed/?paged=3"),
    ("fcl", 2, False, "https://w.test/feed/?page=2"),
    ("blogger", 2, True, "https://w.test/feed/?max-results=150&start-index=151"),
])
def test_page_urls(style, n, backfill, expected):
    assert page_url("https://w.test/feed/", style, n, backfill) == expected


def test_govuk_paging_stops_at_age_floor():
    page1 = b'{"results":[{"title":"New guidance","link":"/guidance/new","description":"d","public_timestamp":"2026-11-20T10:00:00+00:00","format":"guidance"},' \
            b'{"title":"Old","link":"/old","description":"d","public_timestamp":"2026-07-01T10:00:00+00:00","format":"news_story"},' \
            b'{"title":"Person","link":"/p","public_timestamp":"2026-11-20T10:00:00+00:00","format":"person"}]}'
    f = FakeFetcher({"https://www.gov.uk/api/search.json": page1})
    src = {"id": "g", "url": "https://www.gov.uk/api/search.json", "params": {"filter_organisations": "x"}, "paging": "govuk"}
    out = govuk.fetch(src, ctx(f))
    assert [e.title for e in out] == ["New guidance", "Old"]
    assert len(f.calls) == 1  # the old entry stopped paging


OFCOM_LIKE = """<div class="search-results-block"><div class="col-sm-6"><a href="https://www.ofcom.org.uk/tv/bbc/report-on-the-bbc-performance">
BBC continues to deliver for audiences</a> Published: 19 November 2026 TV</div></div>"""
CH4_LIKE = """<div class="c-press-listing"><a href="/press/news/channel-4-new-season">24 Nov 26 News Release Channel 4 announces a new season of drama</a></div>"""


def test_html_list_ofcom_and_channel4():
    ex = {"item": "div.search-results-block div.col-sm-6", "link": 'a[href^="https://www.ofcom.org.uk/"]',
          "title": 'a[href^="https://www.ofcom.org.uk/"]', "date_regex": r"Published:\s*(\d{1,2} [A-Z][a-z]+ \d{4})",
          "date_format": "%d %B %Y"}
    out = html_list.parse_page(OFCOM_LIKE, "https://www.ofcom.org.uk/news", ex)
    assert out[0].title == "BBC continues to deliver for audiences"
    assert out[0].published == datetime(2026, 11, 19, 9, 0, tzinfo=timezone.utc)
    ex4 = {"item": 'div.c-press-listing a[href^="/press/news/"]', "link": "self", "title": "self",
           "title_strip_regex": r"^\s*\d{1,2} [A-Z][a-z]{2} \d{2}\s+News Release\s+",
           "date_regex": r"^\s*(\d{1,2} [A-Z][a-z]{2} \d{2})", "date_format": "%d %b %y"}
    out4 = html_list.parse_page(CH4_LIKE, "https://www.channel4.com/press/news", ex4)
    assert out4[0].title == "Channel 4 announces a new season of drama"
    assert out4[0].url == "https://www.channel4.com/press/news/channel-4-new-season"


def test_html_list_zero_matches_raises():
    with pytest.raises(SourceError):
        html_list.parse_page("<html></html>", "https://x.test/", {"item": "div.nothing"})


def test_embedded_json():
    page = ('<div data-items="[{&quot;heading&quot;:&quot;BBC Studios signs a deal&quot;,&quot;description&quot;:'
            '&quot;&lt;p&gt;A short line.&lt;/p&gt;&quot;,&quot;url&quot;:&quot;https://www.bbcstudios.com/news/bbc-studios-signs-deal/&quot;,'
            '&quot;publishedDate&quot;:&quot;2026-11-19T00:00:00&quot;}]"></div>')
    ex = {"unescape_html": True, "pattern": r'"heading":"(?P<title>.*?)","description":"(?P<abstract>.*?)","url":"(?P<url>https://www\.bbcstudios\.com/news/[^"]+)","publishedDate":"(?P<date>[0-9T:-]+)"'}
    out = embedded_json.parse_page(page, ex)
    assert out[0].title == "BBC Studios signs a deal" and out[0].description == "A short line."
