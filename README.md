# IP & Media Brief

A news reader for two subjects: intellectual property, and the UK broadcasting industry. A scheduled GitHub Actions workflow collects 91 public sources every three hours, stores headlines and short abstracts in `data/items/`, adds short AI summaries where it can, and publishes a static site with GitHub Pages.

- `SPEC.md`: the full specification.
- `MAINTENANCE.md`: what to do when a source breaks, how to add sources and how to cut noise.
- `config/`: sources, topic rules and settings.

The repository stores no article text. Summaries are machine-written: check the source before relying on one.

Find Case Law entries contain public sector information licensed under the Open Justice Licence v1.0. GOV.UK entries contain public sector information licensed under the Open Government Licence v3.0.

## Run locally

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest
.venv/bin/python -m brief probe
.venv/bin/python -m brief collect
.venv/bin/python -m brief build --out _site
```
