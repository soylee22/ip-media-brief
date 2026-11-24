"""Source health, issue text and the run status (SPEC 16). The command always exits 0."""
from __future__ import annotations

from pathlib import Path

from brief import config
from brief.store import read_json


def source_status(src: dict, h: dict | None) -> str:
    if not src.get("enabled", True):
        return "disabled"
    h = h or {}
    if h.get("consecutive_failures", 0) >= 3:
        return "failing"
    if h.get("consecutive_empty", 0) >= 8:
        return "empty"
    return "ok"


def summarise_health(base: Path) -> dict:
    settings = config.load_settings(base)
    sources = config.load_sources(base, include_disabled=True)
    health = read_json(base / "state" / "health.json", {})
    budget = read_json(base / "state" / "ai_budget.json", {})
    report = read_json(base / "state" / "run_report.json", {})
    rows = []
    for s in sources:
        st = source_status(s, health.get(s["id"]))
        rows.append({"id": s["id"], "name": s["name"], "status": st, "h": health.get(s["id"], {})})
    enabled = [r for r in rows if r["status"] != "disabled"]
    failing = [r for r in enabled if r["status"] == "failing"]
    empty = [r for r in enabled if r["status"] == "empty"]
    gemini_rejected = budget.get("gemini_state") == "rejected"
    entries = (report.get("totals") or {}).get("entries")
    share = len(failing) / len(enabled) if enabled else 1.0
    if share > settings["health"]["red_if_failing_share_above"] or entries == 0:
        status = "red"
    elif failing or empty or gemini_rejected:
        status = "amber"
    else:
        status = "green"
    return {"status": status, "rows": rows, "failing": failing, "empty": empty,
            "ok": len(enabled) - len(failing) - len(empty), "gemini_rejected": gemini_rejected}


def issue_body(summary: dict) -> str:
    lines = ["The Brief workflow found sources that need attention.", ""]
    if summary["gemini_rejected"]:
        lines += ["- **Gemini key rejected.** Replace the `GEMINI_API_KEY` secret. See MAINTENANCE.md, section 6.", ""]
    if summary["failing"] or summary["empty"]:
        lines += ["| id | name | status | last error | last success |", "|---|---|---|---|---|"]
        for r in summary["failing"] + summary["empty"]:
            h = r["h"]
            err = (h.get("last_error") or "").replace("|", "/")
            lines.append(f"| `{r['id']}` | {r['name']} | {r['status']} | {err} | {h.get('last_ok_at') or 'never'} |")
        lines += ["", "Fix: see MAINTENANCE.md, section 2."]
    return "\n".join(lines) + "\n"


def run(base: Path | None = None, issue_file: str | None = None, github_output: str | None = None) -> dict:
    base = base or config.root()
    summary = summarise_health(base)
    if issue_file:
        path = Path(issue_file)
        if summary["failing"] or summary["empty"] or summary["gemini_rejected"]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(issue_body(summary), encoding="utf-8")
        elif path.exists():
            path.unlink()
    if github_output:
        with open(github_output, "a", encoding="utf-8") as fh:
            fh.write(f"status={summary['status']}\n")
    return summary
