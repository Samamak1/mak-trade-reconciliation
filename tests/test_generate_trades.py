"""Generator tests: determinism and ground-truth labeling."""

import sqlite3
from dataclasses import asdict

from recon.config import InjectionConfig
from recon.generate_trades import generate, load_sqlite, write_sqlite
from recon.match_engine import match


def test_same_seed_is_fully_deterministic():
    a = generate(n_trades=200, seed=42)
    b = generate(n_trades=200, seed=42)
    assert [asdict(t) for t in a[0]] == [asdict(t) for t in b[0]]
    assert [asdict(t) for t in a[1]] == [asdict(t) for t in b[1]]
    assert a[2] == b[2]


def test_different_seed_differs():
    a = generate(n_trades=200, seed=42)
    b = generate(n_trades=200, seed=43)
    assert [asdict(t) for t in a[0]] != [asdict(t) for t in b[0]]


def test_zero_injection_reconciles_clean():
    inj = InjectionConfig(0.0, 0.0, 0.0, 0.0, 0.0)
    internal, cpty, truth = generate(n_trades=100, seed=7, injection=inj)
    assert truth == []
    r = match(internal, cpty)
    assert r.matched_clean == 100 and r.breaks == []


def test_injected_breaks_are_all_recovered_by_engine(tmp_path):
    """Every labeled injection must be found by the matcher (end to end)."""
    internal, cpty, truth = generate(n_trades=400, seed=42)
    r = match(internal, cpty)
    found = {(b.external_id, b.break_type) for b in r.breaks}
    injected = {(d["external_id"], d["break_type"]) for d in truth}
    missing = injected - found
    assert missing == set(), f"engine missed injected breaks: {missing}"
    # And nothing beyond the injections is flagged (no false positives).
    assert found == injected


def test_sqlite_round_trip(tmp_path):
    db = tmp_path / "trades.sqlite"
    internal, cpty, truth = generate(n_trades=50, seed=1)
    write_sqlite(str(db), internal, cpty, truth)
    got_int, got_cpty = load_sqlite(str(db))
    assert [asdict(t) for t in got_int] == [asdict(t) for t in internal]
    assert [asdict(t) for t in got_cpty] == [asdict(t) for t in cpty]
    con = sqlite3.connect(db)
    n_truth = con.execute("SELECT COUNT(*) FROM injected_breaks").fetchone()[0]
    con.close()
    assert n_truth == len(truth)
