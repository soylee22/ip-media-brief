import json

import httpx
import pytest

from brief import collect, config, summarise
from brief.summarise import parse_answer, validate
from brief.summarise.gemini import Gemini
from tests.conftest import NOW, REPO, FakeFetcher, rss, write_sources

S = config.load_settings(REPO)["summarise"]
SOURCE = ("The Patents Court ruled on Tuesday that Acme's video codec patent is essential to the HEVC standard. "
          "Judge Smith ordered Beta to take a licence on FRAND terms within 30 days. Beta may appeal the decision.")
GOOD = ("The Patents Court ruled that Acme's video codec patent is essential to the HEVC standard. Judge Smith "
        "ordered Beta to take a licence on FRAND terms within 30 days. Beta may appeal the decision, which affects "
        "how video services license codec technology.")


def test_validation_rules():
    assert validate(GOOD, SOURCE, S) is None
    assert "length" in validate("Too short.", SOURCE, S)
    assert validate(GOOD + " We think it matters.", SOURCE, S) == "first person"
    assert validate(GOOD.replace("Judge Smith", "Judge Jones of Microsoft told Google and Amazon that"), SOURCE, S).startswith("entity")
    assert validate("See https://x.test " + GOOD, SOURCE, S) == "format"
    assert parse_answer('```json\n{"summary": "x"}\n```') == "x"
    assert parse_answer('{"summary": ""}') == ""


def gemini_client(responses):
    calls = []

    def handler(request):
        calls.append(request)
        code, body = responses[min(len(calls) - 1, len(responses) - 1)]
        return httpx.Response(code, text=body)
    return httpx.Client(transport=httpx.MockTransport(handler)), calls


def ok(text):
    return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps({"summary": text})}]}}]})


@pytest.fixture
def key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")


def test_gemini_states(key):
    cfg = S["gemini"]
    client, calls = gemini_client([ok(GOOD)])
    g = Gemini(cfg, {}, client=client, sleep=lambda s: None)
    text, state = g.summarise("sys", "user")
    assert state == "ok" and json.loads(text)["summary"] == GOOD
    assert calls[0].headers["x-goog-api-key"] == "test-key-not-real"

    budget = {}
    client, _ = gemini_client([(429, '{"error":{"details":[{"quotaId":"GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}}')])
    assert Gemini(cfg, budget, client=client, sleep=lambda s: None).summarise("s", "u")[1] == "exhausted"
    assert budget["gemini_state"] == "exhausted"

    budget = {}
    client, calls = gemini_client([(404, "model not found"), ok(GOOD)])
    g = Gemini(cfg, budget, client=client, sleep=lambda s: None)
    assert g.summarise("s", "u")[1] == "ok"
    assert budget["gemini_model_in_use"] == cfg["fallback_models"][0]

    budget = {}
    client, _ = gemini_client([(400, "Unknown field thinkingConfig"), ok(GOOD)])
    assert Gemini(cfg, budget, client=client, sleep=lambda s: None).summarise("s", "u")[1] == "ok"
    assert budget["omit_thinking_config"] is True

    budget = {}
    client, _ = gemini_client([(403, "API key not valid")])
    assert Gemini(cfg, budget, client=client, sleep=lambda s: None).summarise("s", "u")[1] == "rejected"


def test_no_key_sets_needs_local(base, tmp_path, monkeypatch):
    write_sources(base, "  - {id: blog, name: Test Blog, desk: ip, adapter: rss, url: 'https://blog.test/feed', fetch_article: false}\n")
    feed = rss([("Codec patent ruling", "https://blog.test/a", SOURCE * 3, "Mon, 23 Nov 2026 10:00:00 GMT")])
    collect.run(base=base, now=NOW, fetcher=FakeFetcher({"https://blog.test/feed": feed}))
    out = tmp_path / "gh_out.txt"
    monkeypatch.setenv("GITHUB_OUTPUT", str(out))
    r = summarise.run("gemini", base=base, now=NOW, fetcher=FakeFetcher({}))
    assert r["state"] == "no_key" and r["needs_local"] is True
    assert "needs_local=true" in out.read_text() and "ollama_model=qwen3:1.7b" in out.read_text()


def test_end_to_end_summary_written(base, key):
    write_sources(base, "  - {id: blog, name: Test Blog, desk: ip, adapter: rss, url: 'https://blog.test/feed', fetch_article: false}\n")
    feed = rss([("Codec patent ruling", "https://blog.test/a", SOURCE * 3, "Mon, 23 Nov 2026 10:00:00 GMT")])
    collect.run(base=base, now=NOW, fetcher=FakeFetcher({"https://blog.test/feed": feed}))
    client, _ = gemini_client([ok(GOOD)])
    r = summarise.run("gemini", base=base, now=NOW, client=client, fetcher=FakeFetcher({}), sleep=lambda s: None)
    assert r["summarised"] == 1
    from brief.store import Store
    item = next(iter(Store(base).items.values()))
    assert item["summary"] == GOOD and item["summary_basis"] == "feed" and item["summary_provider"] == "gemini"
    text = "".join(p.read_text() for p in (base / "data" / "items").glob("*.jsonl"))
    assert "Judge Smith ordered Beta to take a licence on FRAND terms within 30 days. Beta may appeal" in text  # summary only
    assert SOURCE * 2 not in text  # the source text is never stored
