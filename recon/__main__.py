"""CLI entrypoint: python -m recon run --seed 42"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .ai_triage import triage_breaks
from .config import InjectionConfig, ToleranceConfig
from .generate_trades import generate, load_sqlite, write_sqlite
from .match_engine import match
from .report import summary_text, write_csv, write_json, write_summary


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="recon",
        description="Multi-asset trade reconciliation on synthetic data.",
    )
    sub = p.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="generate, reconcile and report")
    run.add_argument("--seed", type=int, default=42, help="RNG seed")
    run.add_argument("--trades", type=int, default=500, help="internal trade count")
    run.add_argument("--db", default="out/trades.sqlite", help="SQLite path")
    run.add_argument("--out-dir", default="out", help="report output directory")
    run.add_argument("--price-rate", type=float, default=0.05)
    run.add_argument("--quantity-rate", type=float, default=0.03)
    run.add_argument("--settlement-rate", type=float, default=0.04)
    run.add_argument("--missing-cpty-rate", type=float, default=0.02)
    run.add_argument("--missing-internal-rate", type=float, default=0.02)
    run.add_argument("--ai-triage", action="store_true",
                     help="use LLM triage if an API key is set (default: rules)")
    return p


def cmd_run(args: argparse.Namespace) -> int:
    inj = InjectionConfig(
        price_rate=args.price_rate,
        quantity_rate=args.quantity_rate,
        settlement_rate=args.settlement_rate,
        missing_counterparty_rate=args.missing_cpty_rate,
        missing_internal_rate=args.missing_internal_rate,
    )
    internal, counterparty, truth = generate(args.trades, args.seed, inj)
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    write_sqlite(args.db, internal, counterparty, truth)
    internal, counterparty = load_sqlite(args.db)  # prove round-trip

    result = match(internal, counterparty, ToleranceConfig())
    triage_breaks(result.breaks, use_llm=args.ai_triage)

    out = Path(args.out_dir)
    write_csv(result, out / "exceptions.csv")
    write_json(result, out / "exceptions.json")
    write_summary(result, out / "summary.txt")
    sys.stdout.write(summary_text(result))
    sys.stdout.write(f"Reports written to {out.resolve()}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
