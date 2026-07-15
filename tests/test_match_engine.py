"""Match engine tests: tolerance boundaries, severity, both-way unmatched."""

from recon.config import ToleranceConfig
from recon.match_engine import match, price_severity, settlement_severity
from recon.models import Trade


def make_trade(**overrides) -> Trade:
    base = dict(
        trade_id="INT-000001", external_id="EXT-000001",
        asset_class="EQUITY", symbol="AAPL", side="BUY",
        quantity=100.0, price=100.0, trade_date="2026-01-05",
        settlement_date="2026-01-07", currency="USD",
        counterparty="CP_ALPHA",
    )
    base.update(overrides)
    return Trade(**base)


def test_identical_trades_match_clean():
    t = make_trade()
    c = make_trade(trade_id="CPT-000001")
    r = match([t], [c])
    assert r.matched_clean == 1
    assert r.breaks == []
    assert r.unmatched_internal == [] and r.unmatched_counterparty == []


def test_price_diff_at_tolerance_is_not_a_break():
    # abs tolerance 0.01 and rel tolerance 5 bps; diff must exceed BOTH.
    tol = ToleranceConfig(price_abs=0.01, price_rel=0.0005)
    t = make_trade(price=100.00)
    c = make_trade(trade_id="CPT-000001", price=100.01)  # exactly at abs tol
    r = match([t], [c], tol)
    assert r.breaks == []


def test_price_diff_just_over_tolerance_is_a_break():
    tol = ToleranceConfig(price_abs=0.01, price_rel=0.0005)
    t = make_trade(price=100.00)
    c = make_trade(trade_id="CPT-000001", price=100.06)  # 6 cents, 6 bps
    r = match([t], [c], tol)
    assert len(r.breaks) == 1
    assert r.breaks[0].break_type == "PRICE"


def test_price_break_needs_both_abs_and_rel_breach():
    # 4 bps on a high-priced stock exceeds abs tol but not rel tol.
    tol = ToleranceConfig(price_abs=0.01, price_rel=0.0005)
    t = make_trade(price=500.00)
    c = make_trade(trade_id="CPT-000001", price=500.20)  # 0.20 abs, 4 bps rel
    assert match([t], [c], tol).breaks == []


def test_price_severity_tiers():
    assert price_severity(100.0, 102.0).value == "HIGH"    # 2% off
    assert price_severity(100.0, 100.5).value == "MEDIUM"  # 50 bps off


def test_quantity_break_is_critical():
    t = make_trade(quantity=100.0)
    c = make_trade(trade_id="CPT-000001", quantity=110.0)
    r = match([t], [c])
    assert len(r.breaks) == 1
    b = r.breaks[0]
    assert b.break_type == "QUANTITY" and b.severity == "CRITICAL"


def test_settlement_severity_tiers():
    assert settlement_severity(1).value == "LOW"
    assert settlement_severity(2).value == "MEDIUM"
    assert settlement_severity(3).value == "MEDIUM"
    assert settlement_severity(4).value == "HIGH"
    assert settlement_severity(-5).value == "HIGH"  # sign-agnostic


def test_settlement_date_break_detected():
    t = make_trade(settlement_date="2026-01-07")
    c = make_trade(trade_id="CPT-000001", settlement_date="2026-01-08")
    r = match([t], [c])
    assert [b.break_type for b in r.breaks] == ["SETTLEMENT_DATE"]
    assert r.breaks[0].severity == "LOW"
    assert r.breaks[0].difference == 1.0


def test_unmatched_internal_only_trade_detected():
    t = make_trade()
    r = match([t], [])
    assert len(r.unmatched_internal) == 1
    assert r.breaks[0].break_type == "MISSING_COUNTERPARTY"
    assert r.breaks[0].severity == "CRITICAL"


def test_unmatched_counterparty_only_trade_detected():
    c = make_trade(trade_id="CPT-000009", external_id="EXT-000009")
    r = match([], [c])
    assert len(r.unmatched_counterparty) == 1
    assert r.breaks[0].break_type == "MISSING_INTERNAL"
    assert r.breaks[0].severity == "CRITICAL"


def test_multiple_field_breaks_on_one_pair():
    t = make_trade(price=100.0, quantity=100.0)
    c = make_trade(trade_id="CPT-000001", price=103.0, quantity=200.0)
    r = match([t], [c])
    kinds = sorted(b.break_type for b in r.breaks)
    assert kinds == ["PRICE", "QUANTITY"]
