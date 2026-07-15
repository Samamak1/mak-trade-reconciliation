"""Core domain models: trades and breaks."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from enum import Enum
from typing import Optional


class AssetClass(str, Enum):
    EQUITY = "EQUITY"
    OPTION = "OPTION"
    FX = "FX"


class BreakType(str, Enum):
    PRICE = "PRICE"
    QUANTITY = "QUANTITY"
    SETTLEMENT_DATE = "SETTLEMENT_DATE"
    MISSING_INTERNAL = "MISSING_INTERNAL"
    MISSING_COUNTERPARTY = "MISSING_COUNTERPARTY"


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class Trade:
    """A single trade record (used for both internal and counterparty)."""

    trade_id: str
    external_id: str
    asset_class: str
    symbol: str
    side: str
    quantity: float
    price: float
    trade_date: str  # ISO yyyy-mm-dd
    settlement_date: str  # ISO yyyy-mm-dd
    currency: str
    counterparty: str

    def settle(self) -> date:
        return date.fromisoformat(self.settlement_date)


@dataclass
class Break:
    """A reconciliation exception."""

    external_id: str
    break_type: str
    severity: str
    field: str
    internal_value: Optional[str]
    counterparty_value: Optional[str]
    difference: Optional[float]
    asset_class: str
    symbol: str
    detail: str = ""
    triage_category: str = ""
    triage_action: str = ""
    triage_source: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
