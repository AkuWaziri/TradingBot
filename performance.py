from dataclasses import dataclass
from math import isfinite

from backtest import BacktestResult


@dataclass(frozen=True)
class PerformanceReport:
    """Derived performance metrics for a completed backtest."""

    initial_balance: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    completed_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    total_fees: float
    average_win: float
    average_loss: float
    largest_loss: float
    profit_factor: float
    buy_and_hold_return_pct: float
    strategy_edge_pct: float


def _finite_non_negative(value: float, name: str) -> None:
    if not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")


def calculate_performance(result: BacktestResult) -> PerformanceReport:
    """Calculate risk and return metrics from an existing backtest result."""
    if result.initial_balance <= 0 or not isfinite(result.initial_balance):
        raise ValueError("result initial_balance must be positive and finite")
    if not result.equity_curve:
        raise ValueError("result equity_curve must not be empty")

    _finite_non_negative(result.max_drawdown_pct, "max_drawdown_pct")

    completed = [trade for trade in result.trades if trade.action == "SELL"]
    winners = [trade.pnl for trade in completed if trade.pnl > 0]
    losers = [trade.pnl for trade in completed if trade.pnl < 0]
    total_fees = sum(trade.fee for trade in result.trades)

    if not isfinite(total_fees) or total_fees < 0:
        raise ValueError("trade fees must be finite and non-negative")

    average_win = sum(winners) / len(winners) if winners else 0.0
    average_loss = sum(losers) / len(losers) if losers else 0.0
    largest_loss = min(losers) if losers else 0.0

    gross_profit = sum(winners)
    gross_loss = abs(sum(losers))
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = float("inf")
    else:
        profit_factor = 0.0

    first_price = result.equity_curve[0]
    if first_price <= 0 or not isfinite(first_price):
        raise ValueError("equity curve must start with a positive finite value")

    # The backtest result does not retain the raw price series. For the
    # baseline engine, the first equity equals initial balance, while the
    # final equity includes any open position. Buy-and-hold is therefore
    # intentionally reported only when no trades were made.
    if not result.trades:
        buy_and_hold_return_pct = (
            (result.final_equity - result.initial_balance)
            / result.initial_balance
            * 100
        )
    else:
        buy_and_hold_return_pct = 0.0

    strategy_edge_pct = result.total_return_pct - buy_and_hold_return_pct

    return PerformanceReport(
        initial_balance=result.initial_balance,
        final_equity=result.final_equity,
        total_return_pct=result.total_return_pct,
        max_drawdown_pct=result.max_drawdown_pct,
        completed_trades=len(completed),
        winning_trades=len(winners),
        losing_trades=len(losers),
        win_rate_pct=result.win_rate_pct,
        total_fees=total_fees,
        average_win=average_win,
        average_loss=average_loss,
        largest_loss=largest_loss,
        profit_factor=profit_factor,
        buy_and_hold_return_pct=buy_and_hold_return_pct,
        strategy_edge_pct=strategy_edge_pct,
    )


def format_report(report: PerformanceReport) -> str:
    """Return a deterministic human-readable backtest report."""
    profit_factor = (
        "inf" if report.profit_factor == float("inf") else f"{report.profit_factor:.2f}"
    )
    return "\n".join(
        (
            "BACKTEST REPORT",
            "─────────────────────────",
            f"Initial balance:    ${report.initial_balance:.2f}",
            f"Final equity:       ${report.final_equity:.2f}",
            f"Return:             {report.total_return_pct:+.2f}%",
            f"Max drawdown:       {report.max_drawdown_pct:.2f}%",
            "",
            f"Completed trades:   {report.completed_trades}",
            f"Winning trades:     {report.winning_trades}",
            f"Losing trades:      {report.losing_trades}",
            f"Win rate:           {report.win_rate_pct:.2f}%",
            f"Profit factor:      {profit_factor}",
            f"Total fees:         ${report.total_fees:.4f}",
            f"Average win:        ${report.average_win:.4f}",
            f"Average loss:       ${report.average_loss:.4f}",
            f"Largest loss:       ${report.largest_loss:.4f}",
            "",
            f"Buy & hold:         {report.buy_and_hold_return_pct:+.2f}%",
            f"Strategy edge:      {report.strategy_edge_pct:+.2f}%",
        )
    )
