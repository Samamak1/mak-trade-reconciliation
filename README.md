# MAK Trade Reconciliation: Exception-Control Prototype

> **Status - portfolio prototype:** This is a synthetic-data demonstration of reconciliation controls and exception governance. It is not connected to an order management system, broker, exchange, counterparty, client, or production environment. It processes no real trades and provides no investment advice or performance claims.

The project models an operational workflow that compares an internal trade record with a counterparty confirmation, identifies breaks, assigns severity, creates audit-friendly reports, and proposes a next action. The emphasis is traceability: injected synthetic breaks are recorded as ground truth so the matching and reporting pipeline can be evaluated against known conditions.

## Business purpose

| Area | Scope |
|---|---|
| Operating problem | Trade records can differ across internal and counterparty systems, creating settlement, financial, and control risk |
| Users modeled | Operations analyst, control owner, reviewer, and escalation stakeholder |
| Control objective | Detect material field breaks, identify records missing on either side, apply a documented severity policy, and preserve evidence for review |
| Delivery | Reproducible generator, matcher, exception reports, local CLI, and optional labeled triage assist |
| Acceptance evidence | Deterministic synthetic ground truth, boundary tests, both-direction unmatched detection, zero-false-positive end-to-end fixture, and report consistency checks |

## My role

I defined the use case, control boundaries, tolerance and severity requirements, exception-reporting needs, acceptance criteria, and review process. The prototype was intentionally scoped around deterministic controls before any optional AI assistance.

## Workflow

1. **Generate** - a seeded generator creates internal and counterparty records for equities, listed options, and FX in SQLite. It injects configurable price, quantity, settlement-date, and missing-trade breaks. Every injected break is also written to a ground-truth table.
2. **Match** - the engine compares records keyed on external ID, applies per-field tolerances from a frozen configuration object, detects unmatched records in both directions, and assigns a documented severity.
3. **Report** - the pipeline writes CSV, JSON, and plain-text exception output with summary counts.
4. **Triage** - deterministic rules propose a category and next action. If an `ANTHROPIC_API_KEY` or `GROQ_API_KEY` is available and `--ai-triage` is explicitly passed, an LLM provides a labeled second opinion. Any API failure falls back to rules.

## Architecture

```text
recon/
  config.py           ToleranceConfig and InjectionConfig dataclasses
  models.py           Trade, Break, Severity, and BreakType
  generate_trades.py  seeded synthetic data and ground-truth break injection
  match_engine.py     tolerance comparison, severity policy, both-way unmatched
  report.py           CSV, JSON, and plain-text reporting
  ai_triage.py        rules-first triage and optional labeled LLM assist
  __main__.py         argparse CLI
tests/                tolerance, severity, determinism, report, and CLI coverage
```

## Severity policy

The policy is implemented in `recon/match_engine.py` and verified in tests.

| Break | Severity |
|---|---|
| Missing on either side | CRITICAL |
| Quantity outside tolerance | CRITICAL |
| Price off by more than 1% | HIGH |
| Price outside tolerance but within 1% | MEDIUM |
| Settlement date off by more than 3 days | HIGH |
| Settlement date off by 2-3 days | MEDIUM |
| Settlement date off by 1 day | LOW |

These are prototype policy choices, not a representation of any specific institution's control framework.

## Quickstart

```bash
pip install -r requirements.txt
python -m recon run --seed 42
```

Outputs are written to `out/`:

- `trades.sqlite`;
- `exceptions.csv`;
- `exceptions.json`; and
- `summary.txt`.

Additional examples:

```bash
python -m recon run --seed 7 --trades 2000 --price-rate 0.10
python -m recon run --seed 42 --ai-triage
```

No external key is required for generation, matching, reporting, or rules-based triage.

## Verification

```bash
pytest -v
```

The test suite covers:

- exact tolerance boundaries, including clean at-tolerance and break just beyond tolerance;
- the requirement that a price difference breach both absolute and relative tolerance;
- every severity tier;
- unmatched detection in both directions;
- an end-to-end assertion that all injected ground-truth breaks are recovered with zero false positives in the controlled fixture;
- SQLite round-trip fidelity;
- CSV/JSON/summary column and count consistency;
- deterministic generation at library and CLI levels; and
- triage behavior with and without configured provider keys.

## Control and design decisions

- **Ground-truth injection:** the generator records every synthetic break, enabling direct comparison between expected and detected exceptions.
- **Centralized configuration:** `ToleranceConfig` and `InjectionConfig` make a run reproducible from seed, trade count, and explicit policy inputs.
- **Dual price tolerance:** a price break must breach both absolute and relative thresholds, reducing sensitivity to harmless noise while preserving a defined basis-point control.
- **Both-direction unmatched detection:** records missing from either the internal or counterparty side are visible.
- **Rules-first triage:** the deterministic path is the control baseline. Optional LLM output is a labeled assist, never an invisible replacement.
- **Synthetic-only boundary:** no credentials, live connectivity, or claims of production data are built into the workflow.

## Acceptance status

| Requirement | Status |
|---|---|
| Seeded multi-asset synthetic records | Implemented and tested |
| Ground-truth break injection | Implemented and tested |
| Field-level tolerance matching | Implemented and tested |
| Both-direction unmatched records | Implemented and tested |
| Severity policy | Implemented and tested |
| CSV, JSON, and text reports | Implemented and tested |
| Rules-based triage | Implemented and tested |
| Optional labeled LLM assist | Implemented; caller must configure and request it |
| Fuzzy matching where external IDs differ | Not implemented |
| Trading-calendar settlement logic | Not implemented |
| Production integration and controls | Not claimed |

## Limitations

- All records, symbols, prices, and breaks are synthetic.
- Matching assumes a shared external ID. Real environments may require controlled fuzzy matching across symbol, side, trade date, quantity, account, and standing-settlement data.
- Settlement differences use calendar days rather than market-specific trading calendars.
- The severity policy is illustrative and would require governance, approvals, thresholds, and change control in a real organization.
- Optional LLM triage is a safe-integration demonstration, not evidence that generated classification outperforms deterministic rules.
- The prototype lacks authentication, authorization, monitoring, case management, operational resilience, and production data governance.

## Authorship and provenance

I defined the use case, control requirements, tolerance and severity policies, acceptance criteria, and review process. Implementation and documentation were developed with AI assistance under my direction and validated against the repository's tests and stated limitations.

Author: Sama Mushtaq
