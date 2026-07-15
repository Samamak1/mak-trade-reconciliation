"""Matching tolerance and break-injection configuration.

All tolerances live in one frozen dataclass so a reconciliation run is
fully described by (data, ToleranceConfig, seed).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToleranceConfig:
    """Per-field matching tolerances.

    Attributes:
        price_abs: absolute price tolerance (same currency units as price).
        price_rel: relative price tolerance as a fraction (0.0005 = 5 bps).
            A price diff is a break only if it exceeds BOTH the absolute
            and the relative tolerance.
        quantity_abs: absolute quantity tolerance. Default 0: any quantity
            difference is a break.
        settlement_days: allowed settlement-date difference in calendar
            days. Default 0: dates must match exactly.
    """

    price_abs: float = 0.01
    price_rel: float = 0.0005
    quantity_abs: float = 0.0
    settlement_days: int = 0


@dataclass(frozen=True)
class InjectionConfig:
    """Rates (0..1) at which synthetic breaks are injected per trade."""

    price_rate: float = 0.05
    quantity_rate: float = 0.03
    settlement_rate: float = 0.04
    missing_counterparty_rate: float = 0.02
    missing_internal_rate: float = 0.02
