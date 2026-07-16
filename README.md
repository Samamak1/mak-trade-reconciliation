# mak-trade-reconciliation

Multi-asset trade reconciliation engine with labeled synthetic data,
field-level tolerance matching, severity tiers, and exception reporting.

Author: Sama Mushtaq

## What it is

A small but complete reconciliation pipeline of the kind that sits between
an internal order management system and counterparty confirmations:

1. **Generate** - a seeded generator produces an internal trade set and a
   counterparty trade set (equities, listed options, FX) in SQLite, and
   injects breaks (price, quantity, settlement date, missing trades) at
   configurable rates. Every injected break is written to a ground-truth
   table, so the matcher can be audited against what was actually broken.
2. **Match** - field-level comparison keyed on external ID, with per-field
   tolerances defined in one frozen dataclass. Unmatched trades are detected
   in both directions. Each break gets a severity tier (CRITICAL / HIGH /
   MEDIUM / LOW) under a documented, tested policy.
3. **Report** - exceptions to CSV, JSON (with summary counts), and a
   plain-text summary table.
4. **Triage (optional)** - a deterministic rule-based classifier suggests a
   category and next action per break. If an `ANTHROPIC_API_KEY` or
   `GROQ_API_KEY` is present in the environment AND `--ai-triage` is passed,
   an LLM second opinion is used instead; every row is labeled with its
   source (`rules` or `llm:<provider>`), and any API failure falls back to
   rules. No key is required for anything in this repo.

## Architecture

```
recon/
  config.py           ToleranceConfig / InjectionConfig dataclasses
  models.py           Trade, Break, Severity, BreakType
  generate_trades.py  seeded synthetic data + break injection -> SQLite
  match_engine.py     tolerance matching, severity policy, both-way unmatched
  report.py           CSV / JSON / plain-text summary
  ai_triage.py        rules-first triage, optional env-keyed LLM assist
  __main__.py         argparse CLI
tests/                pytest suite (tolerances, severities, determinism, CLI)
```

Severity policy (enforced in `match_engine.py`, verified in tests):

| Break | Severity |
|---|---|
| Missing on either side | CRITICAL |
| Quantity outside tolerance | CRITICAL |
| Price off by more than 1% | HIGH |
| Price outside tolerance, within 1% | MEDIUM |
| Settlement date off by more than 3 days | HIGH |
| Settlement date off by 2-3 days | MEDIUM |
| Settlement date off by 1 day | LOW |

## Quickstart

```bash
pip install -r requirements.txt
python -m recon run --seed 42
```

Outputs land in `out/`: `trades.sqlite`, `exceptions.csv`,
`exceptions.json`, `summary.txt`. Useful flags:

```bash
python -m recon run --seed 7 --trades 2000 --price-rate 0.10
python -m recon run --seed 42 --ai-triage   # LLM triage, only if a key is set
```

## Tests

```bash
pytest -v
```

The suite covers: exact tolerance boundaries (at-tolerance is clean,
just-over is a break; price must breach both absolute and relative
tolerance), every severity tier, unmatched detection in both directions,
an end-to-end check that every injected break is recovered with zero false
positives, SQLite round-trip fidelity, report column/count consistency,
seed determinism at both library and CLI level, and triage behavior with
and without keys.

## Design decisions

- **Ground-truth injection.** Breaks are not just randomly sprinkled; each
  one is recorded, so `tests/test_generate_trades.py` can assert the
  matcher finds exactly the injected set - no more, no less.
- **One tolerance config object.** A run is reproducible from
  (seed, trade count, `ToleranceConfig`, `InjectionConfig`) alone.
- **Price breaks require breaching both absolute and relative tolerance**,
  which avoids flagging noise on high-priced instruments while still
  catching real basis-point drift.
- **Rules-first triage.** The LLM path is opt-in, env-keyed, labeled, and
  falls back to rules on any failure, so CI never touches the network.
- Common demo pitfalls avoided: no API keys in code, no fake "live" data,
  breaks are injected and labeled synthetic, every tolerance is tested.

## Limitations

- All trade data is synthetic. Symbols and prices are plausible but not
  real market data, and no market data is fetched from anywhere.
- Matching is keyed on a shared external ID. Real reconciliations often
  need fuzzy keying (symbol + side + date + quantity windows) when IDs do
  not line up; that is out of scope here.
- Settlement tolerance is calendar-day based; a production system would
  use trading calendars per market.
- The LLM triage path is a demonstration of safe optional integration,
  not a claim that LLM classification outperforms the rules.
