import pytest

from backtest import run_backtest


COMMON = dict(
    initial_balance=1_000,
    fast_window=2,
    slow_window=3,
    max_position_pct=0.10,
)


def test_backtest_marks_open_position_to_market():
    result = run_backtest([1, 1, 2, 3, 4], **COMMON)

    assert result.final_equity > result.initial_balance
    assert result.completed_trades == 0
    assert result.equity_curve[-1] == pytest.approx(1_100)


def test_backtest_records_completed_trade_and_pnl():
    result = run_backtest([1, 1, 2, 1], **COMMON)

    assert result.completed_trades == 1
    assert result.winning_trades == 0
    assert result.win_rate_pct == 0
    assert result.trades[0].action == "BUY"
    assert result.trades[1].action == "SELL"
    assert result.trades[1].pnl < 0


def test_backtest_applies_fees():
    no_fee = run_backtest([1, 1, 2, 1], **COMMON, fee_rate=0.0)
    with_fee = run_backtest([1, 1, 2, 1], **COMMON, fee_rate=0.01)

    assert with_fee.final_equity < no_fee.final_equity


def test_backtest_rejects_invalid_prices():
    with pytest.raises(ValueError):
        run_backtest([1, 0, 2], **COMMON)


def test_backtest_rejects_negative_fee():
    with pytest.raises(ValueError):
        run_backtest([1, 2, 3], **COMMON, fee_rate=-0.01)
