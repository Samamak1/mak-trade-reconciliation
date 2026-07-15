"""Report format and triage tests."""

import csv
import json

from recon.ai_triage import triage_breaks, triage_rules
from recon.generate_trades import generate
from recon.match_engine import match
from recon.report import CSV_COLUMNS, summary_text, write_csv, write_json
from recon.models import Break


def _result():
    internal, cpty, _ = generate(n_trades=150, seed=42)
    return match(internal, cpty)


def test_csv_report_has_expected_columns_and_rows(tmp_path):
    r = _result()
    path = write_csv(r, tmp_path / "exceptions.csv")
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows, "expected at least one exception at default injection rates"
    assert list(rows[0].keys()) == CSV_COLUMNS
    assert len(rows) == len(r.breaks)


def test_json_report_summary_counts_are_consistent(tmp_path):
    r = _result()
    path = write_json(r, tmp_path / "exceptions.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["summary"]["total_exceptions"] == len(payload["breaks"])
    assert sum(payload["summary"]["by_severity"].values()) == len(payload["breaks"])
    assert sum(payload["summary"]["by_type"].values()) == len(payload["breaks"])


def test_summary_text_mentions_synthetic_and_counts():
    r = _result()
    text = summary_text(r)
    assert "synthetic" in text.lower()
    assert str(r.total_exceptions) in text
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        assert sev in text


def _break(break_type="PRICE", severity="MEDIUM") -> Break:
    return Break(
        external_id="EXT-000001", break_type=break_type, severity=severity,
        field="price", internal_value="100.0", counterparty_value="100.5",
        difference=0.5, asset_class="EQUITY", symbol="AAPL",
    )


def test_triage_rules_are_deterministic():
    a = triage_rules(_break())
    b = triage_rules(_break())
    assert a == b
    assert a.source == "rules"


def test_triage_default_never_uses_llm(monkeypatch):
    # Even with a key present, use_llm=False must stay on the rules path.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-placeholder")
    breaks = [_break(), _break("QUANTITY", "CRITICAL")]
    triage_breaks(breaks, use_llm=False)
    assert all(b.triage_source == "rules" for b in breaks)
    assert all(b.triage_category for b in breaks)


def test_triage_llm_requested_without_key_falls_back(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    breaks = [_break()]
    triage_breaks(breaks, use_llm=True)
    assert breaks[0].triage_source == "rules"
