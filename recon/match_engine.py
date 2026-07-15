"""Field-level trade matching with per-field tolerances and severity tiers.

Severity policy (documented here, enforced in code, verified in tests):

* MISSING_INTERNAL / MISSING_COUNTERPARTY -> CRITICAL
* QUANTITY outside tolerance              -> CRITICAL (position exposure)
* PRICE: relative diff > 1%               -> HIGH
* PRICE: outside tolerance but <= 1%      -> MEDIUM
* SETTLEMENT_DATE: diff > 3 days -> HIGH; 2-3 days -> MEDIUM; 1 day -> LOW
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List

from .config import ToleranceConfig
from .models import Break, BreakType, Severity, Trade


@dataclass
class MatchResult:
    """Outcome of one reconciliation pass."""

    matched_clean: int = 0
    breaks: List[Break] = field(default_factory=list)
    unmatched_internal: List[Trade] = field(default_factory=list)
    unmatched_counterparty: List[Trade] = field(default_factory=list)

    @property
    def total_exceptions(self) -> int:
        return len(self.breaks)


def price_severity(internal_price: float, cpty_price: float) -> Severity:
    """Severity of a confirmed price break based on relative size."""
    base = abs(internal_price) if internal_price else 1.0
    rel = abs(cpty_price - internal_price) / base
    return Severity.HIGH if rel > 0.01 else Severity.MEDIUM


def settlement_severity(days_diff: int) -> Severity:
    """Severity of a confirmed settlement-date break."""
    d = abs(days_diff)
    if d > 3:
        return Severity.HIGH
    if d >= 2:
        return Severity.MEDIUM
    return Severity.LOW


def _compare_pair(t: Trade, c: Trade, tol: ToleranceConfig) -> List[Break]:
    """Compare one matched internal/counterparty pair field by field."""
    found: List[Break] = []

    price_diff = abs(c.price - t.price)
    rel_base = abs(t.price) if t.price else 1.0
    if price_diff > tol.price_abs and (price_diff / rel_base) > tol.price_rel:
        found.append(Break(
            external_id=t.external_id, break_type=BreakType.PRICE.value,
            severity=price_severity(t.price, c.price).value, field="price",
            internal_value=str(t.price), counterparty_value=str(c.price),
            difference=round(c.price - t.price, 8),
            asset_class=t.asset_class, symbol=t.symbol,
            detail=f"price diff {price_diff:.6f} exceeds tolerance",
        ))

    qty_diff = abs(c.quantity - t.quantity)
    if qty_diff > tol.quantity_abs:
        found.append(Break(
            external_id=t.external_id, break_type=BreakType.QUANTITY.value,
            severity=Severity.CRITICAL.value, field="quantity",
            internal_value=str(t.quantity), counterparty_value=str(c.quantity),
            difference=round(c.quantity - t.quantity, 8),
            asset_class=t.asset_class, symbol=t.symbol,
            detail=f"quantity diff {qty_diff:g} exceeds tolerance",
        ))

    days = (date.fromisoformat(c.settlement_date)
            - date.fromisoformat(t.settlement_date)).days
    if abs(days) > tol.settlement_days:
        found.append(Break(
            external_id=t.external_id,
            break_type=BreakType.SETTLEMENT_DATE.value,
            severity=settlement_severity(days).value, field="settlement_date",
            internal_value=t.settlement_date,
            counterparty_value=c.settlement_date, difference=float(days),
            asset_class=t.asset_class, symbol=t.symbol,
            detail=f"settlement dates differ by {days:+d} day(s)",
        ))
    return found


def _missing_break(t: Trade, break_type: BreakType) -> Break:
    side = "internal" if break_type is BreakType.MISSING_COUNTERPARTY else "counterparty"
    return Break(
        external_id=t.external_id, break_type=break_type.value,
        severity=Severity.CRITICAL.value, field="trade",
        internal_value=t.trade_id if side == "internal" else None,
        counterparty_value=t.trade_id if side == "counterparty" else None,
        difference=None, asset_class=t.asset_class, symbol=t.symbol,
        detail=f"trade present on {side} side only",
    )


def match(
    internal: List[Trade],
    counterparty: List[Trade],
    tol: ToleranceConfig | None = None,
) -> MatchResult:
    """Reconcile two trade sets keyed on external_id.

    Detects unmatched trades in BOTH directions plus field-level breaks
    on matched pairs. Deterministic: output order follows input order.
    """
    tol = tol or ToleranceConfig()
    result = MatchResult()
    cpty_by_id: Dict[str, Trade] = {c.external_id: c for c in counterparty}
    internal_ids = {t.external_id for t in internal}

    for t in internal:
        c = cpty_by_id.get(t.external_id)
        if c is None:
            result.unmatched_internal.append(t)
            result.breaks.append(_missing_break(t, BreakType.MISSING_COUNTERPARTY))
            continue
        pair_breaks = _compare_pair(t, c, tol)
        if pair_breaks:
            result.breaks.extend(pair_breaks)
        else:
            result.matched_clean += 1

    for c in counterparty:
        if c.external_id not in internal_ids:
            result.unmatched_counterparty.append(c)
            result.breaks.append(_missing_break(c, BreakType.MISSING_INTERNAL))
    return result
