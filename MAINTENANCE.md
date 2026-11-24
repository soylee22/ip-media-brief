# Maintenance

Copy this file into the repository as `MAINTENANCE.md`. Every change below can happen in the GitHub website. Open a file, click the pencil icon, edit, and click **Commit changes**.

---

## 1. Normal running

Nothing to do. The Brief workflow runs every 3 hours. Each run collects, summarises, commits the data and updates the site.

---

## 2. A source fails

The "Source health" issue lists each failing source with its last error.

1. Note the source `id` from the issue.
2. Click **Actions**, then **Probe sources**, then **Run workflow**. Type the id in **only**. Run it.
3. Read the error in the run's table. Then follow the matching row.

| Error | Cause | Fix |
|---|---|---|
| HTTP 403 | The site blocks automated requests. | Replace the source with a Google News source: set `adapter: gnews` and `query: 'site:example.com'`, and remove `url`. Or set `enabled: false`. |
| HTTP 404 | The feed moved. | Open the site's home page. Look for an RSS link, or add `/feed/` to the address. Put the new address in `url`. If none exists, use the gnews route above. |
| HTTP 429 | Too many requests. | Wait a day. If it repeats, set `priority: 3` and `paging: none`. |
| HTTP 5xx or timeout | The site is down. | Wait. A short outage fixes itself. |
| `SourceError: 0 items matched` | An HTML page changed its layout. Applies to `ofcom`, `channel4-press`, `enders` and `bbcstudios`. | Ask your AI to update the `extract` block. Use the prompt in section 9. |
| Parse error | The feed is broken. | Try the address in a browser. If it shows a web page instead of a feed, the feed address changed. Treat it as a 404. |

4. After the change, run **Probe sources** for that id again.
5. When the probe shows OK, the next Brief run closes the issue.

To silence a source while you decide, set `enabled: false` and write the reason in `disabled_reason`.

---

## 3. Add a source

1. Find the feed address. Most news sites have one at `/feed/`, `/rss` or `/rss.xml`. A browser extension such as "RSS Feed Reader" can find it.
2. Open `config/sources.yaml`. Copy a block that uses the same adapter. Paste it at the end of the right desk section.
3. Give it a new `id` (lowercase letters, numbers and hyphens only), a `name`, the `desk` and the `url`.
4. Set `priority`: 1 for core, 2 for standard, 3 for background.
5. Commit, then run **Probe sources** with the new id.

For a site with no feed, use Google News:

```yaml
  - id: gn-example
    name: Example (Google News)
    desk: media
    adapter: gnews
    query: 'site:example.com'
    priority: 2
```

---

## 4. Too much noise, or the wrong things marked as picks

1. Open `state/run_report.json`. Its `dropped` list shows up to 20 titles that the filters removed, with the rule that removed each one. Check that nothing important is there.
2. To drop more from one source, add a pattern to that source's `exclude` list. Example: `exclude: ['(?i)\btrailer\b']`.
3. To drop a kind of story everywhere, add a pattern to `noise.title_exclude` in `config/topics.yaml`.
4. To change what counts as a pick, edit `relevance.terms` in `config/topics.yaml`. Raise a weight to push a subject up. Lower `pick_threshold` (default 45) to see more picks.
5. To cap a noisy source, lower its `max_new_per_run`.

Pattern help: `\b` marks a word edge. `(?i)` ignores case. In `topics.yaml`, put `cs:` in front of a short capital acronym such as `cs:\bUS\b`, so it does not match ordinary words.

---

## 5. Turn a desk topic on or off

Topic chips come from `desks.<desk>.topics` in `config/topics.yaml`. Delete a topic block to remove its chip. Add a block with `label` and `patterns` to add one.

---

## 6. Summaries stopped

1. Open `state/ai_budget.json` and read `gemini_state`.
2. `no_key`: the secret is missing. See `01-SETUP-GUIDE.md` part C3.
3. `rejected`: Google refused the key. Create a new key and replace the secret.
4. `exhausted`: the free daily quota ran out. Summaries resume the next day. The local model covers part of the gap.
5. `error`: open the latest Brief run and read the "Summarise with Gemini" step. Give the log to your AI.

To stop all AI summaries, set `summarise.providers: []` in `config/settings.yaml`.

---

## 7. Scheduled runs stopped

GitHub turns off scheduled workflows in a public repository after 60 days without activity. The workflow tries to prevent this.

1. Click **Actions**, then **Brief**.
2. If a banner says the workflow is disabled, click **Enable workflow**.
3. Click **Run workflow** once to restart the cycle.

---

## 8. Once a year

1. Open `https://api.github.com/repos/USERNAME/ip-media-brief` in a browser. The `size` value is the repository size in kilobytes. Above 500,000, ask your AI to move closed years into `data/archive/` as compressed files (SPEC 12.3).
2. Ask your AI to update `requirements.txt` to current versions and to bump the action versions in the workflows. Run the tests.
3. Update `summarise.ollama.version` to a release at least 14 days old.

---

## 9. Prompt for repair requests

Paste this into your AI chat with the files it names:

```
This repository follows 03-SPEC.md. A part has stopped working.

Problem: <one line, for example "Probe shows ofcom: SourceError 0 items matched">
Files attached: config/sources.yaml (the block for <id>), the last 100 lines of the failed run log, and the page HTML if the source is an HTML page.

Find the cause. State it in one sentence. Give me the complete changed files, each headed with its path. Do not change anything else.
```

To give the AI the page HTML: open the page in Chrome, right-click, choose **View Page Source**, select all, copy, and paste it into a text file.
