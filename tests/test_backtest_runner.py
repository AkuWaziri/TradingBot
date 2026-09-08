from pathlib import Path

import pytest

from backtest_runner import run_historical_backtest


CSV = """timestamp,open,high,low,close,volume
2026-01-01T00:00:00Z,100,100,100,100,10
2026-01-01T00:01:00Z,100,101,100,101,10
2026-01-01T00:02:00Z,101,103,101,103,10
2026-01-01T00:03:00Z,103,105,103,105,10
2026-01-01T00:04:00Z,105,106,104,104,10
"""


def test_runner_uses_historical_csv(tmp_path: Path):
    source = tmp_path / "btc.csv"
    source.write_text(CSV, encoding="utf-8")

    report = run_historical_backtest(
        source,
        initial_balance=1_000,
        fast_window=2,
        slow_window=3,
        max_position_pct=0.10,
    )

    assert "BACKTEST REPORT" in report
    assert "Buy & hold:" in report
    assert "Strategy edge:" in report


def test_runner_rejects_missing_file(tmp_path: Path):
    with pytest.raises(ValueError, match="unable to read historical data"):
        run_historical_backtest(tmp_path / "missing.csv")
