"""End-to-end CLI test: python -m recon run --seed 42."""

import json
import subprocess
import sys


def test_cli_run_end_to_end(tmp_path):
    out = tmp_path / "out"
    cmd = [
        sys.executable, "-m", "recon", "run",
        "--seed", "42", "--trades", "120",
        "--db", str(tmp_path / "trades.sqlite"),
        "--out-dir", str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    assert "RECONCILIATION SUMMARY" in proc.stdout
    for name in ("exceptions.csv", "exceptions.json", "summary.txt"):
        assert (out / name).exists(), f"missing {name}"
    payload = json.loads((out / "exceptions.json").read_text(encoding="utf-8"))
    assert payload["summary"]["total_exceptions"] >= 1


def test_cli_is_seed_deterministic(tmp_path):
    outputs = []
    for run_dir in ("a", "b"):
        out = tmp_path / run_dir
        cmd = [
            sys.executable, "-m", "recon", "run",
            "--seed", "99", "--trades", "80",
            "--db", str(tmp_path / f"{run_dir}.sqlite"),
            "--out-dir", str(out),
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        outputs.append((out / "exceptions.csv").read_text(encoding="utf-8"))
    assert outputs[0] == outputs[1]
