"""collect, classify, build and health together, with a fake network."""
import json
from datetime import timedelta

from jsonschema import Draft202012Validator

from brief import build_site, collect, config, health
from brief.classify import Classifier
from brief.store import Store
from tests.conftest import NOW, REPO, FakeFetcher, rss, write_sources

SOURCES = """  - {id: blog, name: Test Blog, desk: ip, adapter: rss, url: 'https://blog.test/feed', priority: 1}
  - {id: trade, name: Trade Paper, desk: media, adapter: rss, url: 'https://trade.test/feed'}
  - {id: gn, name: Wire (Google News), desk: media, adapter: gnews, query: 'site:trade.test'}
  - {id: broken, name: Broken, desk: media, adapter: rss, url: 'https://broken.test/feed'}
"""
D = "Mon, 23 Nov 2026 10:00:00 GMT"
LONG = "The Patents Court ruled that the video codec patent is essential to the standard and must be licensed on FRAND terms. "


def gn_feed(title, publisher):
    return (f'<?xml version="1.0"?><rss version="2.0"><channel><title>G</title><item><title>{title} - {publisher}</title>'
            f'<link>https://news.google.test/articles/abc</link><pubDate>{D}</pubDate>'
            f'<source url="https://trade.test">{publisher}</source></item></channel></rss>').encode()


def pages(blog_title="SEP ruling on video codec patents", trade_title="BBC licence fee review opens"):
    return {
        "https://blog.test/feed": rss([(blog_title, "https://blog.test/sep-ruling?utm_source=rss", LONG * 4, D),
                                       ("Official trailer for the new drama", "https://blog.test/trailer", "x", D)]),
        "https://trade.test/feed": rss([(trade_title, "https://trade.test/bbc-fee", "Government opens a review of the BBC licence fee.", D)]),
        "https://news.google.com/rss/search?q=site%3Atrade.test": gn_feed(trade_title, "Trade Paper"),
    }


def run(base, p):
    return collect.run(base=base, now=NOW, fetcher=FakeFetcher(p))


def test_collect_then_rerun_adds_nothing(base):
    write_sources(base, SOURCES)
    t1 = run(base, pages())
    assert t1["new"] == 2 and t1["failing"] == 1
    assert t1["dropped"] >= 2  # the trailer and the Google News copy of a direct story
    t2 = run(base, pages())
    assert t2["new"] == 0 and t2["revised"] == 0
    items = Store(base).items
    blog = next(i for i in items.values() if i["source_id"] == "blog")
    assert blog["url"] == "https://blog.test/sep-ruling"
    assert "patents-seps" in blog["topics"]
    assert (base / "_work" / "feed_text.json").exists()
    rep = json.loads((base / "state" / "run_report.json").read_text())
    assert any(d["rule"] == "duplicate of a direct source" for d in rep["dropped"])


def test_revision_and_summary_reset(base):
    write_sources(base, SOURCES)
    run(base, pages())
    store = Store(base)
    blog = next(i for i in store.items.values() if i["source_id"] == "blog")
    blog["summary"] = "An earlier summary."
    store.touch(blog["id"])
    store.save()
    t = run(base, pages(blog_title="Completely different headline about trade marks"))
    assert t["revised"] == 1
    blog = Store(base).items[blog["id"]]
    assert blog["revision"] == 2 and blog["summary"] is None and blog["updated_seen_at"]


def test_cluster_and_build_outputs(base):
    write_sources(base, SOURCES + "  - {id: other, name: Other Paper, desk: media, adapter: rss, url: 'https://other.test/feed'}\n")
    p = pages()
    p["https://other.test/feed"] = rss([("BBC licence fee review opens", "https://other.test/fee", "Same story.", D)])
    run(base, p)
    items = Store(base).items.values()
    assert sum(1 for i in items if i["cluster_id"]) == 2
    out = base / "_site"
    r = build_site.build(out, base=base, now=NOW + timedelta(hours=1))
    assert r["hidden_in_clusters"] == 1
    meta = json.loads((out / "data" / "meta.json").read_text())
    assert not list(Draft202012Validator(json.loads((REPO / "schemas/site-meta.schema.json").read_text())).iter_errors(meta))
    day_schema = Draft202012Validator(json.loads((REPO / "schemas/site-day.schema.json").read_text()))
    for f in (out / "data" / "days").glob("*.json"):
        rows = json.loads(f.read_text())
        assert not list(day_schema.iter_errors(rows))
        assert any(row["also"] for row in rows if row["desk"] == "media")
    assert (out / "robots.txt").read_text() == "User-agent: *\nDisallow: /\n"
    assert (out / ".nojekyll").exists()
    assert "__BUILD__" not in (out / "sw.js").read_text()
    first = {f.name: f.read_text() for f in (out / "data" / "days").glob("*.json")}
    build_site.build(out, base=base, now=NOW + timedelta(hours=1))
    assert first == {f.name: f.read_text() for f in (out / "data" / "days").glob("*.json")}


def test_health_issue_file(base, tmp_path):
    write_sources(base, SOURCES)
    for _ in range(3):
        run(base, pages())
    issue = tmp_path / "out" / "issue.md"
    gh_out = tmp_path / "gh.txt"
    s = health.run(base=base, issue_file=str(issue), github_output=str(gh_out))
    assert s["status"] == "amber" and "broken" in issue.read_text()
    assert gh_out.read_text().strip() == "status=amber"
    hj = json.loads((base / "state" / "health.json").read_text())
    hj["broken"]["consecutive_failures"] = 0
    (base / "state" / "health.json").write_text(json.dumps(hj))
    health.run(base=base, issue_file=str(issue))
    assert not issue.exists()


def test_classifier_rules():
    c = Classifier(config.load_topics(REPO))
    assert "us" not in c.jurisdictions("media", "Tell us what you think about radio", "", [])
    assert "us" in c.jurisdictions("ip", "US court rules on patents", "", [])
    assert c.noise_rule("Official trailer for the new drama")
    assert "patents-seps" in c.topics("ip", "SEP licensing deal agreed", "", None)
    score, pick, matched = c.score("BBC licence fee review: streaming levy proposed", "", 1)
    assert pick and "BBC" in matched
    low, low_pick, _ = c.score("Local bakery opens", "", 3)
    assert low == 0 and not low_pick
