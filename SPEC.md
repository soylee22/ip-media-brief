# IP & Media Brief: technical specification

Version 1.0 · 24 November 2026 · Status: agreed for build

This document is the complete build instruction. A builder (a person or an AI) needs this file, the `config/`, `schemas/`, `prompts/`, `workflows/` and `design/` folders, and nothing else. Every number in this file is a default. The YAML files in `config/` hold the values the code reads.

Section numbers are stable. Other files refer to them as "SPEC 9.1".

---

## 1. Purpose and scope

### 1.1 Purpose

The system collects news on two subjects. It publishes one website that the reader can scan on a phone.

1. **IP desk.** News on intellectual property law and practice. Cast wide: patents and standard-essential patents, copyright and AI, trade marks and designs, open-source licensing, licensing deals, court decisions and IP office policy. UK first, then EU, US, China and global.
2. **Media desk.** Commercial awareness of the industry the BBC works in: UK public service broadcasting, the BBC itself, UK and global competitors, streaming platforms, regulation and policy, broadcast technology, deals and production, audio, and the news business. The desk covers the industry, not all of "media". It excludes celebrity news, reviews, trailers and casting.

Each item shows a headline, a one-line abstract, a link to the full article and, where possible, a short AI summary.

### 1.2 In scope

- A Python collector that runs without AI. It reads RSS and Atom feeds, Google News search feeds, the GOV.UK search API and four HTML pages.
- A first large scan (backfill) of up to 90 days, then a run every 3 hours.
- An append-only store in the repository (JSON Lines files) with publish dates, first-seen dates and revision tracking.
- Optional AI summaries through the Gemini API, with a local open model as fallback.
- A static website on GitHub Pages: two desks, topic filters, picks, search, saved items, offline reading.
- Source health monitoring with a GitHub Issue when sources fail.

### 1.3 Out of scope

- Full-text storage or republication of articles.
- Email digests, push notifications and cross-device sync of saved items.
- Login, private hosting or any server other than GitHub Pages.
- Any processing of confidential or work material.

---

## 2. Terms

| Term | Meaning |
|---|---|
| Desk | One of the two subject areas: `ip` or `media`. |
| Source | One entry in `config/sources.yaml`. One source has one adapter and one URL or query. |
| Adapter | The code that reads one kind of source and returns raw entries. SPEC 7. |
| Entry | One raw record from an adapter, before normalisation. |
| Item | One stored record in `data/items/*.jsonl`. Schema: `schemas/item.schema.json`. |
| Abstract | One line, at most 240 characters, taken from the source's own description. |
| Summary | 2 or 3 sentences written by the AI from the article text. At most 90 words. |
| Revision | A later version of a stored item whose title or abstract changed. |
| Cluster | A group of items from different sources with near-identical headlines. |
| Pick | An item whose relevance score is at or above `pick_threshold` (default 35). |
| Run | One execution of the Brief workflow. |
| Backfill | A run in `backfill` mode. It reads older pages of each source. |
| Runner | The GitHub-hosted Ubuntu machine that executes a workflow. |

---

## 3. Decisions already taken

Do not reopen these decisions without the owner's instruction.

| # | Decision | Reason |
|---|---|---|
| D1 | Python 3.12. No Rust. | The libraries for feeds, HTML and article text exist in Python. The work is network-bound, so speed gives no benefit. |
| D2 | GitHub Actions runs everything. GitHub Pages hosts the site. | Free for public repositories. No server to maintain. |
| D3 | Public repository and public site. The site carries noindex and robots.txt disallows all. | Free GitHub Pages requires a public repository. The content is public news. The owner accepted this on 24 Nov 2026. |
| D4 | AI summaries use the Gemini API free tier first. A local open model runs when Gemini is unavailable or out of quota. | GitHub Models, the free AI inside Actions, closed on 30 July 2026. The owner chose the free Gemini tier on 24 Nov 2026 and will read the terms herself. SPEC 21.3. |
| D5 | The collector itself uses no AI. | A site change breaks only one adapter. The owner can repair it with ordinary code. |
| D6 | JSON Lines files in the repository are the database. One file per month. | Readable, diffable, append-friendly, and no binary merge conflicts. |
| D7 | Collection runs every 3 hours. | Several feeds hold only 10 to 12 items, and Deadline publishes 12 items in a few hours. A daily run would miss items. |
| D8 | The site is plain HTML, CSS and JavaScript. No framework and no build tool. | Nothing to install. The owner's AI can read and change every file. |
| D9 | Google News search feeds stand in for sites that block automated requests or have no feed. | Verified on 24 Nov 2026 for Broadcast, Press Gazette, BBC Media Centre, Parliament committees, EBU and others. |
| D10 | Store no article text. Fetch it only in memory to write the summary. | Copyright. A public repository must not republish articles. SPEC 21. |

---

## 4. Architecture

```
config/sources.yaml ──► adapters ──► entries ──► normalise ──► dedupe and revise ──► classify and score
                                                                                          │
                       data/items/YYYY-MM.jsonl ◄── store ◄────────────────────────────────┘
                                 │
                                 ├──► summarise (Gemini, then Ollama) ──► store
                                 │
                                 └──► build ──► _site/ (static files + JSON) ──► GitHub Pages
state/ (HTTP cache, health, AI budget, run report) is read and written by every step.
```

One run executes these commands in order: `collect`, `summarise --provider gemini`, `summarise --provider ollama` (only when needed), `validate`, commit, `build`, `health`, deploy.

---

## 5. Repository layout

Create exactly this tree. The repository name is `ip-media-brief`.

```
ip-media-brief/
├── .gitignore                     # _site/ _work/ _out/ __pycache__/ .pytest_cache/
├── README.md                      # neutral description, no personal data
├── MAINTENANCE.md                 # copy of 04-MAINTENANCE.md from the handoff
├── requirements.txt               # SPEC 5.1
├── pytest.ini                     # testpaths = tests
├── config/
│   ├── settings.yaml
│   ├── sources.yaml
│   └── topics.yaml
├── schemas/
│   ├── item.schema.json
│   ├── sources.schema.json
│   ├── site-meta.schema.json      # SPEC 13.2
│   └── site-day.schema.json       # SPEC 13.3
├── prompts/
│   └── summary.md
├── brief/
│   ├── __init__.py
│   ├── __main__.py                # calls cli.main()
│   ├── cli.py                     # argparse sub-commands, SPEC 18
│   ├── config.py                  # load and validate YAML, apply defaults
│   ├── models.py                  # dataclasses: Source, Entry, Item
│   ├── http.py                    # SPEC 8
│   ├── robots.py                  # robots.txt cache and check
│   ├── adapters/
│   │   ├── __init__.py            # registry: name -> function
│   │   ├── rss.py
│   │   ├── gnews.py
│   │   ├── govuk.py
│   │   ├── fcl.py
│   │   ├── html_list.py
│   │   └── embedded_json.py
│   ├── normalise.py               # SPEC 9
│   ├── dedupe.py                  # SPEC 10.1 to 10.3
│   ├── classify.py                # SPEC 10.4 to 10.7
│   ├── store.py                   # SPEC 12
│   ├── collect.py                 # orchestrates SPEC 7 to 10 and 17
│   ├── summarise/
│   │   ├── __init__.py            # selection, text, validation, budget
│   │   ├── gemini.py
│   │   └── ollama.py
│   ├── build_site.py              # SPEC 13
│   ├── health.py                  # SPEC 16
│   └── probe.py                   # SPEC 18
├── site/                          # SPEC 14
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   ├── sw.js
│   ├── manifest.webmanifest
│   └── icon.svg
├── data/
│   └── items/                     # YYYY-MM.jsonl, written by the workflow only
├── state/                         # written by the workflow only
│   └── .gitkeep
├── tests/
│   ├── fixtures/                  # synthetic files written for the tests
│   └── test_*.py                  # SPEC 19
└── .github/
    └── workflows/
        ├── brief.yml
        └── probe.yml
```

### 5.1 requirements.txt

These exact versions installed together on Python 3.13 on 24 November 2026.

```
feedparser==6.0.14
httpx==0.28.1
beautifulsoup4==4.15.0
lxml==6.1.3
trafilatura==2.4.0
PyYAML==6.0.4
rapidfuzz==3.14.6
python-dateutil==4.0.0
jsonschema==4.26.0
pytest==9.2.0
respx==0.23.1
```

---

## 6. Settings

`config/settings.yaml` holds every tunable value. The comments in that file explain each key. Rules:

1. Load the file with `yaml.safe_load`.
2. Fail the run with a clear message if a required key is missing.
3. Expand `~` in paths.
4. Read secrets only from environment variables. Never from YAML.

The only secret is `GEMINI_API_KEY`. The workflow passes it from the repository secret of the same name.

---

## 7. Sources and adapters

### 7.1 Source registry

`config/sources.yaml` lists 96 sources. 91 are enabled: 42 on the IP desk and 49 on the media desk. `05-SOURCES.md` explains each choice and each exclusion. `schemas/sources.schema.json` defines every field.

Apply `defaults` to every source, then the source's own keys. Validate the result against the schema. Reject the run if two sources share an `id`.

Skip a source when `enabled: false`.

### 7.2 Adapter contract

Each adapter is a function:

```python
def fetch(source: Source, ctx: FetchContext) -> list[Entry]
```

`FetchContext` gives the HTTP client, the mode (`normal` or `backfill`), the age floor (a UTC datetime), the page limit and the set of known item ids.

`Entry` has these fields. Use `None` when a value is absent.

| Field | Type | Notes |
|---|---|---|
| `url` | str | Absolute link to the article. |
| `title` | str | Raw title. |
| `description` | str or None | Raw summary or description, may contain HTML. |
| `content` | str or None | Raw full content when the feed gives it. Never stored. |
| `published` | datetime or None | UTC. |
| `updated` | datetime or None | UTC. |
| `publisher` | str or None | Only for gnews. |
| `extra` | dict | Adapter-specific values, for example a neutral citation. |

An adapter must not raise for one bad entry. It skips that entry and logs it. An adapter raises `SourceError` only when the whole source fails.

### 7.3 Paging (gap filling and backfill)

Paging rules apply to every adapter whose source has `paging` other than `none`.

1. Fetch page 1.
2. Stop when the page holds an entry whose canonical id is already in the store.
3. Stop when the oldest entry on the page is older than the age floor.
4. Stop when the page holds no entries.
5. Stop at `max_pages_normal` (3) in normal mode or `max_pages_backfill` (20) in backfill mode.
6. Otherwise fetch the next page.

Page URL patterns:

| Style | Page N URL |
|---|---|
| `wordpress` | Add `paged=N` to the query string. Page 1 has no parameter. |
| `blogger` | Set `max-results=150` and `start-index=1+150*(N-1)`. |
| `fcl` | Add `page=N` to the query string. |
| `govuk` | Set `count=100` and `start=100*(N-1)`. |

### 7.4 `rss` adapter

1. GET the URL with the rules in SPEC 8.
2. Parse the bytes with `feedparser.parse`.
3. For each entry, take `link`, `title`, `summary`, `content[0].value`, `published_parsed` and `updated_parsed`.
4. Convert the parsed times to UTC datetimes.
5. Raise `SourceError` when the response has no `<rss>`, `<feed>` or `<rdf:RDF>` root and feedparser finds no entries.

### 7.5 `gnews` adapter

Google News search feeds stand in for blocked or feedless sites.

1. Build the URL: `https://news.google.com/rss/search?q=<query>&hl=en-GB&gl=GB&ceid=GB:en`. URL-encode the query. Do not add `when:`. Google ignores it for some results.
2. Parse with feedparser.
3. Take `publisher` from the entry's `source.title`. Set `via = "Google News"` on the item.
4. Remove the suffix `" - <publisher>"` from the title.
5. Set `description` to None. The Google description repeats the title only.
6. Keep the Google article link as `url`. It redirects to the publisher in a browser.
7. Set `fetch_article` to false for every gnews source. The redirect needs JavaScript.

Google returns some items years old. The age floor in SPEC 9.5 removes them.

### 7.6 `govuk_search` adapter

1. GET `https://www.gov.uk/api/search.json` with the source `params`, plus `order=-public_timestamp`, `count` and `start` from SPEC 7.3, and `fields=title,link,description,public_timestamp,format`.
2. For each result, build `url = "https://www.gov.uk" + link`.
3. Use `description` as the description and `public_timestamp` as the published time.
4. Skip results whose `format` is `organisation`, `person`, `ministerial_role` or `world_location`.

The search API returned `total: 2722` for the IPO on 24 Nov 2026.

### 7.7 `fcl` adapter (Find Case Law)

1. GET the Atom URL. Parse with feedparser.
2. Take the title, link and published time.
3. Take the court name from `author.name` when present.
4. Find the neutral citation in the title, summary or id with this pattern: `\[\d{4}\] (UKSC|UKPC|EWCA (Civ|Crim)|EWHC|UKUT|UKFTT|EAT)\s*\d+(\s*\([A-Za-z]+\))?`.
5. Set `extra = {"court": ..., "citation": ...}`.
6. Never fetch the judgment page. SPEC 21.2 explains why.

### 7.8 `html_list` adapter

Use this adapter only for the 3 HTML sources. Each source has an `extract` block.

1. Check robots.txt. Skip the source with a warning if robots.txt disallows the path.
2. GET the page. Parse with BeautifulSoup and lxml.
3. Select every element that matches `extract.item`.
4. Inside each element, select `extract.link`. The value `self` means the element itself. Read `href` and make it absolute against the page URL.
5. Read the title from `extract.title` in the same way. Collapse whitespace.
6. Remove any text that matches `extract.title_strip_regex`.
7. Search the element's text with `extract.date_regex`. Parse group 1 with `extract.date_format` as a London-local date at 09:00, then convert to UTC.
8. Drop elements with no link or a title under 15 characters.
9. Raise `SourceError` when zero elements match `extract.item`. A zero count means the site changed its HTML.

The Ofcom, Channel 4 and Enders selectors were derived from the live pages on 24 Nov 2026.

### 7.9 `embedded_json` adapter

BBC Studios puts its news list in an HTML-escaped JSON attribute.

1. Check robots.txt. GET the page.
2. If `extract.unescape_html` is true, apply `html.unescape` to the page text.
3. Apply `extract.pattern` with `re.finditer`. The pattern has the named groups `title`, `abstract`, `url` and `date`.
4. Unescape JSON string escapes in each group with `json.loads('"' + value + '"')`.
5. Strip HTML tags from `abstract`.
6. Parse `date` as ISO 8601 London-local time.
7. Raise `SourceError` when the pattern finds no match.

---

## 8. HTTP rules

1. Use one `httpx.Client` per run with `follow_redirects=True` and HTTP/1.1.
2. Send `User-Agent: ip-media-brief/1.0 (personal feed reader)` from settings. Do not imitate a browser. The Guardian returned 403 to a browser string and 200 to the honest string on 24 Nov 2026.
3. Send `Accept: application/rss+xml, application/atom+xml, application/xml;q=0.9, text/html;q=0.8, */*;q=0.5`.
4. Set the timeout to 20 seconds.
5. Retry twice after a timeout, a connection error or a 5xx response. Wait 3 seconds, then 9 seconds.
6. Do not retry 4xx responses.
7. Keep at most one request in flight per host. Wait 2 seconds between requests to the same host.
8. Run up to 8 hosts in parallel with a thread pool.
9. Use conditional GET. Store `ETag` and `Last-Modified` per URL in `state/http_cache.json`. Send `If-None-Match` and `If-Modified-Since`. Treat 304 as success with zero entries.
10. Use conditional GET for page 1 only. Never for later pages.
11. Cache robots.txt per host for the run. Use `urllib.robotparser`. Check it for `html_list`, `embedded_json` and article fetches only. Feeds are published for automated readers.
12. Never send cookies or credentials.

---

## 9. Normalisation

### 9.1 Canonical URL

Apply these steps in order.

1. Parse the URL with `urllib.parse.urlsplit`.
2. Lowercase the scheme and the host.
3. Remove the port when it is 80 for http or 443 for https.
4. Remove the fragment.
5. Remove every query parameter whose name starts with `utm_`.
6. Remove these query parameters: `fbclid`, `gclid`, `dclid`, `mc_cid`, `mc_eid`, `ref`, `ref_src`, `cmpid`, `CMP`, `ito`, `at_medium`, `at_campaign`, `ocid`, `s_cid`, `sr_share`, `taid`, `rss`, `src`, `feed`, `share`.
7. Sort the remaining parameters by name. Keep their values.
8. Remove one trailing slash from the path unless the path is `/`.
9. Keep http and https as given. Do not remove `www.`.

`id` is the first 16 hexadecimal characters of `sha256(canonical_url.encode("utf-8"))`.

Test cases (SPEC 19 uses them):

| Input | Canonical |
|---|---|
| `https://Example.com/a/?utm_source=x&b=2&a=1#top` | `https://example.com/a?a=1&b=2` |
| `https://example.com:443/` | `https://example.com/` |
| `http://example.com/news/item/` | `http://example.com/news/item` |

### 9.2 Title

1. Unescape HTML entities. Remove tags. Collapse whitespace. Strip.
2. Replace curly quotes with straight quotes.
3. Cut to 300 characters at a word boundary.
4. Drop the entry when the title has fewer than 3 characters.

### 9.3 Abstract

1. Take `description`. Use `content` when `description` is empty.
2. Remove tags with BeautifulSoup `get_text(" ")`. Unescape entities. Collapse whitespace.
3. Remove text that matches any of these patterns (ignore case):
   - `The post .* appeared first on .*$`
   - `(Continue|Read) (reading|more).*$`
   - `\[(…|\.\.\.)\]`
   - `^By [A-Z][\w.'-]+( [A-Z][\w.'-]+){0,3}\s*[,|:-]?\s*`
4. Remove the title from the start of the text when the text starts with it.
5. If the text is longer than 240 characters, cut it at the first sentence end after 60 characters. If it is still longer, cut at the last space before character 239 and add "…".
6. For `fcl` items, set the abstract to `"<court> judgment. <citation>."`. Leave out a part that is missing.
7. For `gnews` items, set the abstract to an empty string.

### 9.4 Dates

1. `published_at` is the entry's published time. Use the updated time when published is missing.
2. Set `published_at` to null when it is more than 1 day in the future.
3. Write all datetimes as ISO 8601 UTC with a `Z` suffix and whole seconds.
4. `first_seen_at` is the start time of the run that first stored the item.

### 9.5 Age floor

1. Normal mode: drop an entry when `published_at` is older than `max_item_age_days` (14).
2. Backfill mode: drop an entry when `published_at` is older than the `--days` value (default 90).
3. Keep an entry with a null `published_at`. Its display date becomes `first_seen_at`.

### 9.6 Fingerprint

`fingerprint` is the first 16 hexadecimal characters of `sha256(title + "\n" + abstract)` after SPEC 9.2 and 9.3.

---

## 10. Deduplication, classification and scoring

### 10.1 Same URL

1. Compute the id. If no stored item has this id, the entry is new.
2. If a stored item has this id and the same fingerprint, do nothing. Do not touch any field. This rule keeps diffs small.
3. If the fingerprint differs, create a revision: add 1 to `revision`, set `updated_seen_at` to the run time, and replace `title`, `abstract` and `fingerprint`.
4. On a revision, compare the old and new titles with `rapidfuzz.fuzz.token_set_ratio`. If the ratio is below 80, set `summary` and its four related fields to null and `summary_attempts` to 0. The summariser then writes a new summary.

### 10.2 Same story, different sources (clusters)

1. Normalise each title for comparison: lowercase, remove punctuation, collapse whitespace.
2. Compare each new item with stored items whose display date is within ±3 days (`cluster.window_days`).
3. Two items match when `token_set_ratio` is at or above 88 (`cluster.title_similarity`).
4. A gnews item that matches an item from a direct source with the same publisher is a duplicate. Drop it.
5. Other matches join a cluster. `cluster_id` is the id of the leader.
6. The leader is the item with the best source priority. Ties go to the earliest `first_seen_at`.

Different outlets often rewrite a headline. A test pair about one story scored 74 on 24 Nov 2026, so clusters catch near-copies only. This limit is accepted.

### 10.3 Per-source filters

1. When a source has `include` patterns, keep an entry only if its title or abstract matches one of them.
2. Drop an entry whose title matches a source `exclude` pattern.
3. Drop an entry whose title matches a global `noise.title_exclude` pattern in `topics.yaml`.
4. Keep at most `max_new_per_run` new items per source per run, or 10 times that in backfill mode. Keep the newest.
5. Record up to 20 dropped titles, each with the rule that dropped it, in `state/run_report.json`. The owner uses this list to tune the filters.

### 10.4 Pattern syntax

1. A pattern without a prefix matches with `re.IGNORECASE`.
2. A pattern that starts with `cs:` matches with case. Remove the prefix before compiling.
3. Compile every pattern once at start-up. Fail the run with the file and pattern name when a pattern does not compile.

### 10.5 Topics

1. Use the topic patterns of the item's own desk.
2. Give each topic 2 points for every pattern that matches the title and 1 point for every pattern that matches the abstract.
3. Assign the topics with at least 1 point, highest first, at most 4.
4. When no topic scores, use the source `topics_hint`.

### 10.6 Cross-desk

Add the other desk to `also_desks` when the title matches a pattern of a topic listed for that desk under `cross_desk_topics`.

### 10.7 Jurisdictions

Start with the source `jurisdictions`. Add every jurisdiction whose patterns match the title or abstract. Remove duplicates. For an IP item with an empty list, use `["global"]`.

### 10.8 Relevance score and picks

1. Start with the source priority points: 20, 10 or 0.
2. For each `relevance.terms` pattern, add its weight when the title matches. Add half the weight, rounded down, when only the abstract matches.
3. Add 5 points for each other source in the item's cluster, up to 15.
4. Cap the score at 100.
5. Set `pick` to true when the score is at least 35 (`pick_threshold`).
6. Store up to 8 matched term patterns in `matched_terms`, in the form the reader can understand. Remove `\b`, `cs:` and regex syntax for display.

Recalculate the score of a cluster leader when its cluster grows.

---

## 11. Summaries

### 11.1 Selection

Select items that meet every condition:

1. `summary` is null.
2. `summary_attempts` is less than 2.
3. The display date is within `summarise.max_item_age_days` (7).
4. The source is not an `fcl` source.

Order the selection by score, highest first, then by `first_seen_at`, newest first.

### 11.2 Source text

1. If the source has `fetch_article: true` and `paywalled: false`, and robots.txt allows it, GET the article URL with the SPEC 8 rules.
2. Extract the text with `trafilatura.extract(html, include_comments=False, include_tables=False, favor_precision=True)`.
3. If the article text is shorter than 400 characters (`min_source_chars`), use the entry's feed content or description instead, cleaned as in SPEC 9.3 steps 1 and 2. `collect` writes this text for new items to `_work/feed_text.json` as `{id: text}`. `summarise` reads that file in the same job. `_work/` is in `.gitignore`, so the text never reaches the repository.
4. If the text is still shorter than 400 characters, set `summary_attempts` to 2 and skip the item.
5. Cut the text to 1,200 words (`max_input_words`) at the last sentence end before the limit.
6. Set `summary_basis` to `article` or `feed` to record which text the summary used.

A later run cannot read feed text from an earlier run, because `_work/` does not persist. Such an item uses the article route or stays without a summary.

### 11.3 Prompt

Use `prompts/summary.md` exactly. Fill the placeholders. Do not change the rules in the SYSTEM text without a test.

### 11.4 Validation

Reject an answer that breaks any rule:

1. The answer parses as JSON with a string field `summary`.
2. An empty `summary` means "not enough facts". Accept it as final. Set `summary_attempts` to 2 and keep `summary` null.
3. The summary has 25 to 90 words.
4. The summary contains no `http`, no `www.`, no line break and no character from `#*` at the start.
5. The summary does not match `cs:\b(I|We|we|Our|our|My|my)\b`.
6. The summary does not contain "the article", "this article", "the author" or "as an AI" (ignore case).
7. Entity check: collect the capitalised words and numbers in the summary with `\b([A-Z][\w&'-]+|\d[\d,.%]*)\b`. Remove each sentence's first word and the words `The`, `A`, `An`, `This`, `It`, `UK`, `EU`, `US`. At least 70% of the rest must appear in the source text, ignoring case. When the list is empty, the check passes.

When an answer fails, retry once with the same provider. Add this line to the user text: `Your previous answer broke a rule. Follow every rule exactly.` When the retry fails, add 1 to `summary_attempts` and move on.

### 11.5 Gemini provider

1. Skip the provider when `GEMINI_API_KEY` is empty. Report the state `no_key`.
2. Read `state/ai_budget.json`. Reset its counters when its `date` is not today's UTC date.
3. Stop when the run has made `per_run_cap` (120) calls or the day has made `daily_call_cap` (400) calls. Count every call, including retries.
4. Wait at least 5 seconds between calls (`min_seconds_between_calls`).
5. Build the request from `prompts/summary.md`.
6. On HTTP 200, parse `candidates[0].content.parts[0].text`.
7. On HTTP 429, read the body. If it contains `PerDay` or `per day`, mark the day as exhausted and stop. Otherwise wait 60 seconds and retry once. A second 429 stops the provider for this run.
8. On HTTP 400 that mentions `thinking`, remove `thinkingConfig` and retry once. Record the change in `state/ai_budget.json` so later calls omit it.
9. On HTTP 404, try each model in `fallback_models`. Record the model that works in `state/ai_budget.json` as `gemini_model_in_use`.
10. On HTTP 401 or 403, stop. Report the state `rejected`. The health check reports "Gemini key rejected".
11. Never log the key, the request headers or the full request body.
12. Set `summary_provider = "gemini"` and `summary_model` to the model name used.

At the end, write these lines to the file named in `$GITHUB_OUTPUT` when that variable exists:

```
needs_local=<true|false>
ollama_version=<settings value>
ollama_model=<settings value>
ollama_model_key=<model name with ":" replaced by "-">-<version>
```

`needs_local` is true when eligible items remain, `ollama` is in `providers`, and the Gemini state is `no_key`, `exhausted`, `rejected` or `error`. It is false when Gemini only reached its per-run cap. The next run continues.

### 11.6 Ollama provider

1. The workflow installs Ollama and pulls the model only when `needs_local` is true.
2. Pin `settings.summarise.ollama.version` to the newest release that is at least 14 days old when you build. v0.40.18 appeared on 24 Nov 2026. The Linux asset name is `ollama-linux-amd64.tar.zst`.
3. Use the model `qwen3:1.7b` (Apache-2.0 licence). It was listed in the Ollama library on 24 Nov 2026.
4. Send requests to `http://127.0.0.1:11434/api/chat` as `prompts/summary.md` shows.
5. Stop after 15 items (`per_run_cap`) or 25 minutes (`max_run_minutes`). Time out one item after 120 seconds.
6. Apply the same validation as SPEC 11.4.
7. Set `summary_provider = "ollama"` and `summary_model = "qwen3:1.7b"`.

### 11.7 Things the summariser must never do

1. Never store the source text in `data/` or `state/`.
2. Never summarise an `fcl` item.
3. Never send anything except public article text and the headline.

---

## 12. Storage

### 12.1 Item files

1. Path: `data/items/YYYY-MM.jsonl`. The month is the UTC month of `first_seen_at`.
2. One JSON object per line. Each object validates against `schemas/item.schema.json`.
3. Serialise with `json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))`.
4. Sort the lines by `first_seen_at`, then `id`.
5. End the file with one newline. Use UTF-8 and LF line ends.
6. Write a changed file to a temporary path, then replace the old file with `os.replace`.
7. Write only the files whose content changed.
8. At start-up, load every file into a dictionary keyed by `id`. Fail the run when two lines share an id.

A revision rewrites the line in the file of the item's original month.

### 12.2 State files

| File | Content |
|---|---|
| `state/http_cache.json` | `{url: {"etag": str or null, "last_modified": str or null}}` |
| `state/health.json` | `{source_id: {"last_attempt_at", "last_ok_at", "last_status", "last_error", "consecutive_failures", "consecutive_empty", "entries_last_run", "new_last_run", "new_by_day": {"YYYY-MM-DD": int}}}`. Keep 14 days in `new_by_day`. |
| `state/ai_budget.json` | `{"date": "YYYY-MM-DD", "gemini_calls": int, "gemini_state": str, "gemini_model_in_use": str, "omit_thinking_config": bool, "ollama_calls": int}` |
| `state/run_report.json` | Start and end time, mode, totals and per-source counts. Key `dropped` holds up to 20 records `{"source_id", "title", "rule"}`. Overwritten each run. |
| `state/backfill.json` | `{"last_backfill_finished_at": ISO time or null}` |

Serialise state files with `indent=1` and `sort_keys=True` so diffs stay readable.

### 12.3 Size

The media desk produces about 150 to 250 items a day after filters. One item takes about 1 to 1.5 KB. One year is about 100 MB of JSON Lines before Git compression. GitHub warns at 1 GB per repository. Review the size once a year. A later version can move closed years to `data/archive/YYYY.jsonl.gz`.

---

## 13. Site build

### 13.1 Output

`python -m brief build --out _site` writes:

```
_site/
├── index.html, styles.css, app.js, sw.js, manifest.webmanifest, icon.svg   (copied from site/)
├── robots.txt         User-agent: * / Disallow: /
├── .nojekyll          empty file
└── data/
    ├── meta.json
    ├── days/YYYY-MM-DD.json      one file per display date, newest 60 days
    └── search/YYYY-MM.json       one file per display month, newest 12 months
```

The workflow uploads `_site/` to Pages. Do not commit `_site/`. The `.gitignore` file lists `_site/`, `_work/`, `_out/`, `__pycache__/` and `.pytest_cache/`.

The display date of an item is the Europe/London date of `published_at`. Use `first_seen_at` when `published_at` is null.

### 13.2 meta.json

Write `schemas/site-meta.schema.json` from this description and validate the output against it in a test.

| Field | Content |
|---|---|
| `generated_at` | ISO UTC time of the build. |
| `title`, `subtitle` | From settings. |
| `desks` | `{desk_id: {"label", "accent", "topics": {topic_id: label}}}` from `topics.yaml`. |
| `days` | List of `{"date", "ip", "media", "picks"}`, newest first. Counts exclude cluster members. |
| `months` | List of `YYYY-MM` strings that have a search file, newest first. |
| `sources` | List of `{"id", "name", "desk", "homepage", "priority", "status", "last_ok_at", "new_7d"}`. Status is `ok`, `empty`, `failing` or `disabled`. |
| `health` | `{"status": "green" or "amber" or "red", "ok": int, "failing": int, "empty": int}` |
| `summary_label` | For example `AI summary (Gemini). Check the source before you rely on it.` |
| `licence_notes` | The unique `licence_note` values of enabled sources. |
| `version` | Short Git commit hash from `GITHUB_SHA`, or `local`. |
| `backfill_until` | ISO UTC end time of the last backfill run, from `state/backfill.json`, or null. SPEC 17. |

### 13.3 Day files

Each day file is a JSON array. Write `schemas/site-day.schema.json` from this description. Each element has:

`id, desk, also_desks, title, url, source_name, publisher, via, published_at, first_seen_at, abstract, summary, summary_model, summary_basis, topics, jurisdictions, score, pick, paywalled, revision, updated_seen_at, also`

`also` is a list of `{"source_name", "url"}` for the other members of the item's cluster. Leave cluster members out of the day files. List them only in their leader's `also`.

Sort each array by `published_at` (or `first_seen_at`), newest first.

### 13.4 Search files

Each search file is a JSON array of arrays, to keep the file small:

`[id, display_date, desk, title, source_name, url, topics_joined_by_comma, pick_as_0_or_1]`

### 13.5 Rules

1. The build is deterministic. The same data gives byte-identical output, apart from `generated_at` and `version`.
2. The build reads only `data/`, `state/`, `config/` and `site/`.
3. The build never makes a network request.

---

## 14. Front end

`design/mockup.html` is the visual reference. It shows the layout, colours, type and card anatomy with sample data. Build `site/` to match it. Where this section and the mockup differ, this section wins.

### 14.1 Views

1. **Today** (default). A briefing strip, the top picks, then the feed grouped by day.
2. **Saved.** Items the reader saved, newest saved first.
3. **Sources.** Every source with its status, last success and items in 7 days. The licence notes appear here.

### 14.2 Header

1. The site title on the left.
2. The text "Updated 06:21, Tue 24 Nov" in London time from `meta.generated_at`.
3. A health dot: green, amber or red. A tap opens the Sources view.
4. A theme toggle: system, light, dark.

### 14.3 Controls

1. A desk switch with three options: **IP**, **Media**, **Both**. Remember the last choice.
2. Topic chips for the current desk. The chips scroll sideways on a phone. Several chips can be active. No active chip means all topics.
3. A **Picks only** toggle.
4. A sort control: **Newest** or **Most relevant**.
5. A search box. It filters the loaded days at once as the reader types. Below the results, a button **Search older months** loads the search files.

### 14.4 Briefing strip

One line at the top of Today: "Since your last visit: 23 IP · 41 Media · 6 picks". Count items with `first_seen_at` after the previous visit. On the first visit, count today's items.

Below it, show up to 5 picks per visible desk from the last 48 hours, highest score first.

### 14.5 Feed

1. Group cards under day headings: "Today", "Yesterday", then "Mon 22 Nov".
2. Insert a divider "New since your last visit" above the first card the reader has not seen.
3. Load meta.json and the newest 3 day files first. Load the next day file when the reader scrolls near the end. Use `IntersectionObserver`.
4. Show an empty state when a filter matches nothing. Offer one button to clear the filters.

### 14.6 Card

From top to bottom:

1. A coloured edge: indigo for IP, teal for Media.
2. A meta line: source name (and "via Google News" in small text when `via` is set), time ("14:05" for today, "22 Nov" for older days), and badges.
3. Badges: **Pick**, **Updated** (revision above 1), **Paywall**, **+2 sources** (length of `also`).
4. The headline as a link. Open it in a new tab with `rel="noopener noreferrer"`. Use a serif face.
5. The abstract on one or two lines. Clamp at 2 lines on a phone.
6. When `summary` exists, a **Summary** button. A tap expands the summary in place. Under it, show `meta.summary_label` in small text.
7. Topic tags and jurisdiction tags as small labels. A tap on a topic tag sets that topic filter.
8. Actions: **Save** (star), **Copy link**. Mark the card as read when the reader opens the link.
9. When `also` has entries, a line "Also: Guardian, Deadline" with links.

Read cards show a lighter headline colour.

### 14.7 Saved items

1. Store a full copy of each saved item in `localStorage`, so a saved item survives after its day file drops off the site.
2. Provide **Export saved** (download a JSON file) and **Import saved** (read a JSON file) in the Saved view.

### 14.8 Local storage

Use these keys. Wrap every read and write in try and catch. The site must work when storage is blocked.

| Key | Value |
|---|---|
| `brief.v1.lastVisit` | ISO time of this visit. |
| `brief.v1.prevVisit` | ISO time of the previous visit. |
| `brief.v1.desk` | `ip`, `media` or `both`. |
| `brief.v1.topics` | Array of active topic ids per desk. |
| `brief.v1.picksOnly`, `brief.v1.sort`, `brief.v1.theme` | Control states. |
| `brief.v1.saved` | `{id: item}` |
| `brief.v1.read` | `{id: epoch_ms}`. Keep the newest 5,000 entries. |

Update `prevVisit` from `lastVisit` once per visit, when the page loads.

### 14.9 Keyboard

`j` and `k` move between cards. `o` opens the focused card's link. `s` saves it. `/` focuses the search box. `1`, `2`, `3` select IP, Media, Both. `Esc` clears the search.

### 14.10 Offline and install

1. `manifest.webmanifest`: name, short name "Brief", `start_url` and `scope` equal to `base_path`, `display: standalone`, theme colour, and the SVG icon.
2. `sw.js`: cache the app shell at install. Use network first for `data/` files, with a cached copy as fallback. Use cache first for the shell. Change the cache name on each build by appending `meta.version`.
3. Show "Offline. Showing the last copy." when a data fetch fails.

### 14.11 Visual rules

1. Define colours as CSS custom properties on `:root`. Redefine them for dark mode under `@media (prefers-color-scheme: dark)` and under `:root[data-theme="dark"]`.
2. Body text: system sans-serif, 16 px, line height 1.5. Headlines: `ui-serif, Georgia, serif`, 18 px on a phone, 19 px on a desktop.
3. Layout: one column, maximum width 760 px, 16 px side gutters on a phone. No horizontal page scroll at 360 px width.
4. Text contrast meets WCAG 2.2 AA: 4.5 to 1 for body text.
5. Every control is a `<button>` or a link. Show a visible focus ring. Toggles use `aria-pressed`.
6. Respect `prefers-reduced-motion`.
7. Load no web fonts, no images and no third-party scripts. The site makes requests only to its own origin.

### 14.12 Page head

```html
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<meta name="referrer" content="no-referrer">
<title>IP &amp; Media Brief</title>
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icon.svg" type="image/svg+xml">
```

### 14.13 Budgets

1. HTML, CSS and JavaScript together: under 60 KB before compression.
2. First paint with data on a mid-range phone on 4G: under 3 seconds.
3. Use relative URLs everywhere, so the site works under `/ip-media-brief/`.

---

## 15. Workflows

### 15.1 Brief (`workflows/brief.yml`)

Copy the file to `.github/workflows/brief.yml` without changes. It does this:

1. Runs at 17 minutes past every third hour, UTC, and on demand.
2. Installs Python 3.12 and the requirements.
3. Runs the tests and checks the JavaScript syntax. A failure stops the run, so bad code never changes data.
4. Runs `collect`, then `summarise --provider gemini`.
5. Installs Ollama and runs `summarise --provider ollama` only when the Gemini step set `needs_local=true`.
6. Runs `validate`, commits `data/` and `state/`, and pushes.
7. Builds `_site/` and runs `health`. Opens, updates or closes the "Source health" issue.
8. Calls the workflow enable API. Public repositories lose scheduled workflows after 60 days without activity. This call is a safeguard. GitHub does not document whether it resets the timer.
9. Uploads the site and deploys it in a second job. The second job waits for the artifact. This pattern fixed a "Found 0 artifact(s)" race in another project on 24 Nov 2026.
10. A third job fails the run when health is red, after the deploy. The site still updates, and GitHub sends a failure email.

A `concurrency` group stops two runs from writing data at the same time.

### 15.2 Probe sources (`workflows/probe.yml`)

Runs only on demand. It tests every source, or the ids given, from the runner. It writes a Markdown table to the run page. It changes no data.

### 15.3 Settings the owner sets once

1. Settings, Pages, Source: **GitHub Actions**.
2. Settings, Actions, General, Workflow permissions: **Read and write permissions**.
3. Settings, Secrets and variables, Actions: secret `GEMINI_API_KEY`.

`01-SETUP-GUIDE.md` gives the clicks.

---

## 16. Health

1. A source attempt succeeds when the adapter returns without `SourceError`. A 304 response counts as success.
2. On success, set `consecutive_failures` to 0. When the attempt returned zero entries and the source had entries before, add 1 to `consecutive_empty`. Otherwise set it to 0.
3. On failure, add 1 to `consecutive_failures` and store the status code or error class and a message of at most 200 characters.
4. Source status:
   - `failing`: `consecutive_failures` is 3 or more.
   - `empty`: `consecutive_empty` is 8 or more (one day of runs).
   - `disabled`: `enabled: false`.
   - `ok`: all other cases.
5. Overall status:
   - `red`: more than 40% of enabled sources are failing, or the run fetched zero entries in total.
   - `amber`: at least one source is failing or empty, or Gemini is `rejected`.
   - `green`: all other cases.
6. When any source is failing or empty, or Gemini is `rejected`, write the issue body to the path given by `--issue-file`. Create the parent folder when it does not exist. List each problem source with its id, name, status, last error, last success and the line "Fix: see MAINTENANCE.md, section 2." When there is no problem, delete that file if it exists.
7. Write `status=<green|amber|red>` to the path given by `--github-output`.
8. The `health` command always exits with code 0. The health-gate job decides the run result.

---

## 17. Backfill (the first big scan)

1. Start it from the Actions tab: workflow **Brief**, **Run workflow**, mode `backfill`, days `90`.
2. Backfill uses the SPEC 7.3 paging rules with `max_pages_backfill` (20) and the age floor from `--days`.
3. Feeds without paging return only their current items. `05-SOURCES.md` lists the expected depth for each source.
4. `first_seen_at` is the run time for every backfilled item. The site groups items by display date (SPEC 13.1), so old items fall under their own dates.
5. The prevVisit logic would mark every backfilled item as new. To stop that, `meta.json` carries `backfill_until`: the end time of the last backfill run. The front end does not count items with `first_seen_at` at or before `backfill_until` in the briefing strip, and does not place the "new" divider above them.
6. The summariser selects only items from the last 7 days. The daily cap spreads them over the first days.
7. Expect 2,000 to 5,000 items and 20 to 60 minutes. Most of the time is the 2-second gap between requests to one host.

`collect` writes the end time of a backfill run to `state/backfill.json` as `{"last_backfill_finished_at": "..."}`.

---

## 18. Command line

Run every command as `python -m brief <command>` from the repository root.

| Command | Options | Effect |
|---|---|---|
| `collect` | `--mode normal\|backfill`, `--days N`, `--only id1,id2` | SPEC 7 to 10. Writes `data/` and `state/`. Prints a summary table. |
| `summarise` | `--provider gemini\|ollama`, `--max N` | SPEC 11. |
| `validate` | none | Validates config, every item line and the state files. Exits 1 on any error. |
| `build` | `--out DIR` | SPEC 13. |
| `health` | `--issue-file PATH`, `--github-output PATH` | SPEC 16. Always exits 0. |
| `probe` | `--only id1,id2`, `--report PATH` | Fetches each source and parses it. Writes a Markdown table: id, adapter, HTTP status, entries, newest date, oldest date, error. Writes nothing to `data/` or `state/`. |
| `stats` | none | Prints item counts by desk, source and month. |

Every command prints a one-line result at the end, for example `collect: 87 ok, 4 failing, 213 new, 6 revised, 41 dropped`.

---

## 19. Tests

Use pytest. Tests make no network requests. Mock HTTP with `respx`. Write synthetic fixture files. Do not copy real articles into fixtures.

| File | Tests |
|---|---|
| `test_config.py` | The shipped YAML loads and validates. Every pattern compiles. Duplicate ids fail. |
| `test_normalise.py` | The three canonical URL cases in SPEC 9.1. Id stability. Title cleaning. Each abstract rule in SPEC 9.3. Future dates become null. |
| `test_adapters.py` | rss (RSS 2.0 and Atom fixtures), gnews (publisher suffix removal), govuk (JSON fixture, paging stops at the age floor), fcl (court and citation), html_list (Ofcom-like and Channel 4-like fixtures, zero matches raises), embedded_json (BBC Studios-like fixture). |
| `test_paging.py` | Each paging style builds the right URL. Paging stops at a known id. |
| `test_dedupe.py` | The same URL with tracking parameters gives one item. A changed title gives revision 2 and clears the summary. A small change keeps the summary. Similar titles form a cluster. A gnews duplicate of a direct item is dropped. |
| `test_classify.py` | "Tell us what you think" gets no `us` tag. "US court rules" gets `us`. "SEP licensing" gets `patents-seps`. A trailer headline is dropped. Score and pick thresholds. |
| `test_summarise.py` | Each validation rule passes and fails. The Gemini client handles 200, 429 per minute, 429 per day, 400 about thinking, 404 with fallback and 401. A missing key gives `no_key`. `needs_local` is written correctly. |
| `test_store.py` | Write then read gives the same items. Output is byte-stable. Only changed month files are rewritten. |
| `test_build.py` | Outputs validate against the site schemas. robots.txt and .nojekyll exist. Cluster members leave the day files. The build is deterministic. |
| `test_health.py` | Status rules. The issue file appears and disappears. The command exits 0. |
| `test_no_secrets.py` | No file in the repository matches `AIza[0-9A-Za-z_-]{35}`. No item line holds a key outside the item schema. |

---

## 20. Acceptance criteria

The build is complete when every check passes. Record each result.

| # | Check | How to verify |
|---|---|---|
| A1 | All tests pass on GitHub. | The "Run tests" step in a Brief run is green. |
| A2 | At least 80% of enabled sources work from the runner. | Probe sources run. Count OK rows. Disable or repair the rest (MAINTENANCE.md). |
| A3 | The backfill completes. | Brief run in backfill mode is green within 90 minutes. `data/items/` holds at least 1,000 items. `validate` passes. |
| A4 | A second normal run straight after adds no duplicates. | Run Brief twice. The second summary line shows 0 or a few new items and 0 revised. |
| A5 | The site works on a phone. | Open the Pages URL on a phone. No sideways scroll. Both desks, chips, picks and search work. A headline opens the source. |
| A6 | Summaries appear. | After one day, at least 70% of non-paywalled, non-gnews, non-fcl items from the last 24 hours show a Summary button. |
| A7 | The site is not indexable. | `/robots.txt` shows `Disallow: /`. The page source holds `noindex`. |
| A8 | No article text and no secrets are in the repository. | `test_no_secrets.py` passes. A search of `data/` finds no field outside the schema. |
| A9 | Health alerts work. | Change one source URL to a wrong path on a branch, or wait for a real failure. After 3 runs, the "Source health" issue opens. |
| A10 | Offline reading works. | Open the site, then switch the phone to aeroplane mode and reload. The last copy shows. |

---

## 21. Legal, privacy and safety rules

### 21.1 Copyright

1. Store and publish only the headline, the abstract (at most 240 characters from the publisher's own feed description), the link, the AI summary in new words, and metadata.
2. Never commit article text. Never copy, store or hotlink images.
3. Credit each item to its source by name on its card.

### 21.2 Find Case Law

The Open Justice Licence (read on 24 Nov 2026) states: "You need additional permission (a separate licence) for computational analysis of Find Case Law judgments (including indexing by search engines)." So:

1. List judgments from the Atom feed only: title, court, citation, date and link.
2. Never fetch, summarise or index judgment text.
3. Show the licence note: "Contains public sector information licensed under the Open Justice Licence v1.0."

### 21.3 Gemini terms

Google's Gemini API Additional Terms, read on 24 Nov 2026, contain these sentences:

- "Use of Google AI Studio and Gemini API is for developers building with Google AI models for professional or business purposes, not for consumer use."
- "You may use only Paid Services when making API Clients available to users in the European Economic Area, Switzerland, or the United Kingdom."
- On unpaid services: Google uses submitted content and responses "to provide, improve, and develop Google products", and "human reviewers may read, annotate, and process your API input and output."

The terms define "API Clients" as a "website, application, or other service" that uses the services. This site may fall within that definition. The owner chose the free tier on 24 Nov 2026 and will read the terms herself (D4). The code works the same on the paid tier. Billing is an account setting, not a code change.

Send Gemini only public article text and headlines. Never send work material.

### 21.4 Privacy

1. Put no personal data in the repository: no name, employer, role, email address or phone number.
2. Commit as `github-actions[bot]`.
3. Keep the user agent free of contact details.
4. Store reading history and saved items only in the reader's browser.

### 21.5 Neutral content

The site aggregates news. It publishes no commentary. Summaries are neutral by prompt rule 6. An employer's guidance on staff online activity may apply to a public site. The owner should check that guidance at induction.

### 21.6 Audience

The Gemini terms bar services "directed towards or likely to be accessed by individuals under the age of 18". The site is a professional news reader with noindex. It is not directed at children.

---

## 22. Build phases

Build in this order. Do not start a phase until the previous phase passes its check.

| Phase | Work | Check |
|---|---|---|
| P0 | Repository, layout, `requirements.txt`, `pytest.ini`, empty `brief` package, a passing placeholder test, both workflows. | The Run tests step is green on GitHub. |
| P1 | `config.py`, `models.py`, `validate`. | `test_config.py` passes. |
| P2 | `http.py`, `robots.py`, the six adapters, paging, `probe`. | `test_adapters.py` and `test_paging.py` pass. A Probe sources run shows at least 80% OK. |
| P3 | `normalise.py`, `dedupe.py`, `classify.py`, `store.py`, `collect`. | Tests pass. A normal Brief run commits `data/items/` and `validate` passes. |
| P4 | `build_site.py`, the site files from the mockup. | `test_build.py` passes. The Pages URL works on a phone (A5, A7). |
| P5 | Summariser, Gemini provider, Ollama provider. | `test_summarise.py` passes. Summaries appear on the site. |
| P6 | `health`, the issue step, the keepalive step, the health gate. | `test_health.py` passes. A9 passes. |
| P7 | Backfill run. Tune `topics.yaml` and source filters with `state/run_report.json`. | A3, A4, A6, A8 and A10 pass. |

---

## 23. Known limits

1. Feeds expose recent items only. Backfill depth depends on the source.
2. Google News links redirect through Google. The gnews adapter cannot fetch article text, so these items have no summary.
3. Paraphrased headlines about one story stay separate items (SPEC 10.2).
4. Some sites that answered a UK home connection may block GitHub's runners. The Probe sources run shows which.
5. Free Gemini quotas change without notice. Blogs reported about 500 calls a day for Flash-Lite models in October 2026. Google's rate-limit page says limits apply per project and points to AI Studio for the actual values.
6. GitHub may delay scheduled runs at busy times.
7. The store loads every item into memory. This works to about 200,000 items, which is about 3 years.
