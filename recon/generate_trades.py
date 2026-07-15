"""Seeded synthetic trade generation with labeled break injection.

Generates an internal trade set and a counterparty trade set across
equities, options and FX, writes both to SQLite, and injects breaks
(price / quantity / settlement-date / missing) at configurable rates.
Every injected break is recorded in an ``injected_breaks`` ground-truth
table so the match engine's findings can be audited. All data is
synthetic and clearly labeled as such.
"""

from __future__ import annotations

import random
import sqlite3
from dataclasses import asdict
from datetime import date, timedelta
from typing import Dict, List, Tuple

from .config import InjectionConfig
from .models import Trade

EQUITY_SYMBOLS = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "UNH", "HD", "KO"]
FX_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]
OPTION_UNDERLYINGS = ["SPY", "QQQ", "AAPL", "TSLA"]
COUNTERPARTIES = ["CP_ALPHA", "CP_BRAVO", "CP_CHARLIE", "CP_DELTA"]
SIDES = ["BUY", "SELL"]

_BASE_PRICES: Dict[str, float] = {
    "AAPL": 190.0, "MSFT": 410.0, "NVDA": 120.0, "JPM": 200.0,
    "XOM": 110.0, "UNH": 500.0, "HD": 350.0, "KO": 62.0,
    "EURUSD": 1.085, "GBPUSD": 1.27, "USDJPY": 152.0,
    "AUDUSD": 0.66, "USDCAD": 1.36,
    "SPY": 5.40, "QQQ": 4.10, "TSLA": 12.5,
}


def _make_trade(rng: random.Random, idx: int) -> Trade:
    """Build one synthetic internal trade."""
    asset = rng.choice(["EQUITY", "EQUITY", "OPTION", "FX"])
    trade_dt = date(2026, 1, 5) + timedelta(days=rng.randint(0, 120))
    if asset == "EQUITY":
        symbol = rng.choice(EQUITY_SYMBOLS)
        qty = float(rng.randrange(100, 5000, 100))
        price = round(_BASE_PRICES[symbol] * rng.uniform(0.9, 1.1), 2)
        settle = trade_dt + timedelta(days=2)
        ccy = "USD"
    elif asset == "OPTION":
        und = rng.choice(OPTION_UNDERLYINGS)
        expiry = trade_dt + timedelta(days=rng.choice([14, 30, 60]))
        strike = round(_BASE_PRICES.get(und, 100.0) * rng.uniform(30, 40))
        symbol = f"{und} {expiry.strftime('%y%m%d')}C{strike:08d}"
        qty = float(rng.randrange(1, 200))
        price = round(_BASE_PRICES[und] * rng.uniform(0.5, 2.0), 2)
        settle = trade_dt + timedelta(days=1)
        ccy = "USD"
    else:
        symbol = rng.choice(FX_PAIRS)
        qty = float(rng.randrange(100_000, 5_000_000, 50_000))
        price = round(_BASE_PRICES[symbol] * rng.uniform(0.98, 1.02), 5)
        settle = trade_dt + timedelta(days=2)
        ccy = symbol[3:]
    return Trade(
        trade_id=f"INT-{idx:06d}",
        external_id=f"EXT-{idx:06d}",
        asset_class=asset,
        symbol=symbol,
        side=rng.choice(SIDES),
        quantity=qty,
        price=price,
        trade_date=trade_dt.isoformat(),
        settlement_date=settle.isoformat(),
        currency=ccy,
        counterparty=rng.choice(COUNTERPARTIES),
    )


def generate(
    n_trades: int = 500,
    seed: int = 42,
    injection: InjectionConfig | None = None,
) -> Tuple[List[Trade], List[Trade], List[dict]]:
    """Generate internal + counterparty trade sets with labeled breaks.

    Returns:
        (internal_trades, counterparty_trades, injected_breaks) where
        injected_breaks is the ground-truth list of what was perturbed.
    """
    inj = injection or InjectionConfig()
    rng = random.Random(seed)
    internal = [_make_trade(rng, i) for i in range(n_trades)]
    counterparty: List[Trade] = []
    truth: List[dict] = []

    for t in internal:
        roll = rng.random()
        if roll < inj.missing_counterparty_rate:
            truth.append({"external_id": t.external_id,
                          "break_type": "MISSING_COUNTERPARTY", "field": "trade"})
            continue  # counterparty never booked it
        c = Trade(**{**asdict(t), "trade_id": t.trade_id.replace("INT", "CPT")})
        roll2 = rng.random()
        if roll2 < inj.price_rate:
            # Bump must exceed BOTH default tolerances (abs 0.01, rel 5 bps)
            # so every injected price break is detectable by construction.
            mag = max(t.price * rng.choice([0.002, 0.02]), 0.02)
            c.price = round(t.price + mag * rng.choice([-1, 1]), 6)
            truth.append({"external_id": t.external_id,
                          "break_type": "PRICE", "field": "price"})
        elif roll2 < inj.price_rate + inj.quantity_rate:
            c.quantity = t.quantity + rng.choice([1, 10, 100])
            truth.append({"external_id": t.external_id,
                          "break_type": "QUANTITY", "field": "quantity"})
        elif roll2 < inj.price_rate + inj.quantity_rate + inj.settlement_rate:
            shift = rng.choice([1, 2, 3, 5])
            c.settlement_date = (t.settle() + timedelta(days=shift)).isoformat()
            truth.append({"external_id": t.external_id,
                          "break_type": "SETTLEMENT_DATE", "field": "settlement_date"})
        counterparty.append(c)

    n_extra = int(round(n_trades * inj.missing_internal_rate))
    for j in range(n_extra):
        ghost = _make_trade(rng, 900_000 + j)
        ghost.trade_id = f"CPT-{900_000 + j:06d}"
        counterparty.append(ghost)
        truth.append({"external_id": ghost.external_id,
                      "break_type": "MISSING_INTERNAL", "field": "trade"})
    return internal, counterparty, truth


_SCHEMA = """
CREATE TABLE IF NOT EXISTS {name} (
    trade_id TEXT PRIMARY KEY, external_id TEXT NOT NULL,
    asset_class TEXT, symbol TEXT, side TEXT,
    quantity REAL, price REAL, trade_date TEXT,
    settlement_date TEXT, currency TEXT, counterparty TEXT
);
"""


def write_sqlite(
    db_path: str,
    internal: List[Trade],
    counterparty: List[Trade],
    truth: List[dict],
) -> None:
    """Persist both trade sets and the injection ground truth to SQLite."""
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        for name, rows in (("internal_trades", internal),
                           ("counterparty_trades", counterparty)):
            cur.execute(f"DROP TABLE IF EXISTS {name}")
            cur.execute(_SCHEMA.format(name=name))
            cur.executemany(
                f"INSERT INTO {name} VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                [tuple(asdict(t).values()) for t in rows],
            )
        cur.execute("DROP TABLE IF EXISTS injected_breaks")
        cur.execute("CREATE TABLE injected_breaks "
                    "(external_id TEXT, break_type TEXT, field TEXT)")
        cur.executemany(
            "INSERT INTO injected_breaks VALUES (?,?,?)",
            [(d["external_id"], d["break_type"], d["field"]) for d in truth],
        )
        con.commit()
    finally:
        con.close()


def load_sqlite(db_path: str) -> Tuple[List[Trade], List[Trade]]:
    """Load both trade sets back from SQLite."""
    con = sqlite3.connect(db_path)
    try:
        out: List[List[Trade]] = []
        for name in ("internal_trades", "counterparty_trades"):
            rows = con.execute(
                "SELECT trade_id, external_id, asset_class, symbol, side, "
                "quantity, price, trade_date, settlement_date, currency, "
                f"counterparty FROM {name}").fetchall()
            out.append([Trade(*r) for r in rows])
        return out[0], out[1]
    finally:
        con.close()
