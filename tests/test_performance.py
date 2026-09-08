import pytest

from backtest import run_backtest
from performance import calculate_performance, format_report


COMMON = dict(
    initial_balance=1_000,
    fast_window=2,
    slow_window=3,
    max_position_pct=0.10,
)


def test_performance_counts_wins_losses_and_fees():
    result = run_backtest([1, 1, 2, 3, 2, 1], **COMMON, fee_rate=0.01)
    report = calculate_performance(result)

    assert report.completed_trades == 1
    assert report.winning_trades == 0
    assert report.losing_trades == 1
    assert report.win_rate_pct == 0
    assert report.total_fees > 0
    assert report.average_win == 0
    assert report.average_loss < 0
    assert report.largest_loss == report.average_loss
    assert report.profit_factor == 0


def test_performance_handles_no_trades():
    result = run_backtest([1, 1, 1, 1], **COMMON)
    report = calculate_performance(result)

    assert report.completed_trades == 0
    assert report.winning_trades == 0
    assert report.losing_trades == 0
    assert report.total_fees == 0
    assert report.profit_factor == 0
    assert report.buy_and_hold_return_pct == 0


def test_performance_report_is_human_readable():
    result = run_backtest([1, 1, 2, 3, 2, 1], **COMMON)
    report = calculate_performance(result)
    text = format_report(report)

    assert "BACKTEST REPORT" in text
    assert "Return:" in text
    assert "Max drawdown:" in text
    assert "Profit factor:" in text


def test_performance_rejects_empty_equity_curve():
    from backtest import BacktestResult

    result = BacktestResult(
        initial_balance=1000,
        final_equity=1000,
        total_return_pct=0,
        max_drawdown_pct=0,
        completed_trades=0,
        winning_trades=0,
        win_rate_pct=0,
        trades=(),
        equity_curve=(),
    )

    with pytest.raises(ValueError, match="equity_curve"):
        calculate_performance(result)
