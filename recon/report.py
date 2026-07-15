"""Exception reporting: CSV + JSON + plain-text summary table."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import List

from .match_engine import MatchResult

CSV_COLUMNS = [
    "external_id", "break_type", "severity", "field", "internal_value",
    "counterparty_value", "difference", "asset_class", "symbol", "detail",
    "triage_category", "triage_action", "triage_source",
]

SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]


def write_csv(result: MatchResult, path: str | Path) -> Path:
    """Write one row per break to CSV. Returns the path written."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for b in result.breaks:
            writer.writerow(b.to_dict())
    return path


def write_json(result: MatchResult, path: str | Path) -> Path:
    """Write the full result (breaks + counts) as JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": {
            "matched_clean": result.matched_clean,
            "total_exceptions": result.total_exceptions,
            "unmatched_internal": len(result.unmatched_internal),
            "unmatched_counterparty": len(result.unmatched_counterparty),
            "by_severity": dict(Counter(b.severity for b in result.breaks)),
            "by_type": dict(Counter(b.break_type for b in result.breaks)),
        },
        "breaks": [b.to_dict() for b in result.breaks],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def summary_text(result: MatchResult) -> str:
    """Render a plain-text summary table (fixed-width, no dependencies)."""
    by_sev = Counter(b.severity for b in result.breaks)
    by_type = Counter(b.break_type for b in result.breaks)
    lines: List[str] = []
    lines.append("RECONCILIATION SUMMARY (synthetic data)")
    lines.append("=" * 46)
    lines.append(f"{'Matched clean':<32}{result.matched_clean:>10}")
    lines.append(f"{'Total exceptions':<32}{result.total_exceptions:>10}")
    lines.append(f"{'Unmatched internal-only':<32}{len(result.unmatched_internal):>10}")
    lines.append(f"{'Unmatched counterparty-only':<32}{len(result.unmatched_counterparty):>10}")
    lines.append("-" * 46)
    lines.append("By severity:")
    for sev in SEVERITY_ORDER:
        lines.append(f"  {sev:<30}{by_sev.get(sev, 0):>10}")
    lines.append("By break type:")
    for bt in sorted(by_type):
        lines.append(f"  {bt:<30}{by_type[bt]:>10}")
    lines.append("=" * 46)
    return "\n".join(lines) + "\n"


def write_summary(result: MatchResult, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(summary_text(result), encoding="utf-8")
    return path
