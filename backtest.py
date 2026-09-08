from dataclasses import dataclass
from typing import Sequence

from execution import PaperAccount
from risk import approve_order
from strategy import generate_signal


@dataclass(frozen=True)
class Trade:
    index: int
    action: str
    price: float
    quantity: float
    fee: float
    pnl: float = 0.0


@dataclass(frozen=True)
class BacktestResult:
    initial_balance: float
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    completed_trades: int
    winning_trades: int
    win_rate_pct: float
    trades: tuple[Trade, ...]
    equity_curve: tuple[float, ...]


def _validate_prices(prices: Sequence[float]) -> None:
    if not prices:
        raise ValueError("prices must not be empty")
    if any(price <= 0 for price in prices):
        raise ValueError("all prices must be positive")


def run_backtest(
    prices: Sequence[float],
    initial_balance: float,
    fast_window: int,
    slow_window: int,
    max_position_pct: float,
    fee_rate: float = 0.0,
) -> BacktestResult:
    """Run the deterministic baseline strategy against a price series.

    Orders are filled at the current test price. Fees are charged on notional.
    The engine only buys when flat and only sells when a position exists.
    An open position is marked to market at the final price; it is not force-sold.
    """
    _validate_prices(prices)
    if initial_balance <= 0:
        raise ValueError("initial_balance must be positive")
    if fee_rate < 0:
        raise ValueError("fee_rate must be non-negative")

    account = PaperAccount(initial_balance)
    trades: list[Trade] = []
    equity_curve: list[float] = []
    entry_cost = 0.0

    for index, price in enumerate(prices):
        signal = generate_signal(prices[: index + 1], fast_window, slow_window)

        if signal.action == "BUY" and account.position.quantity == 0:
            fee_adjusted_price = price * (1 + fee_rate)
            decision = approve_order(
                account.cash, fee_adjusted_price, max_position_pct
            )
            if decision.approved:
                quantity = decision.quantity
                notional = quantity * price
                fee = notional * fee_rate
                account.buy(quantity, price + (fee / quantity))
                entry_cost = notional + fee
                trades.append(Trade(index, "BUY", price, quantity, fee))

        elif signal.action == "SELL" and account.position.quantity > 0:
            quantity = account.position.quantity
            notional = quantity * price
            fee = notional * fee_rate
            proceeds = notional - fee
            account.sell(quantity, price - (fee / quantity))
            pnl = proceeds - entry_cost
            trades.append(Trade(index, "SELL", price, quantity, fee, pnl))
            entry_cost = 0.0

        equity_curve.append(account.equity(price))

    final_equity = equity_curve[-1]
    peak = equity_curve[0]
    max_drawdown = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak if peak else 0.0
        max_drawdown = max(max_drawdown, drawdown)

    completed = [trade for trade in trades if trade.action == "SELL"]
    winners = [trade for trade in completed if trade.pnl > 0]
    win_rate = (len(winners) / len(completed) * 100) if completed else 0.0
    total_return = (final_equity - initial_balance) / initial_balance * 100

    return BacktestResult(
        initial_balance=initial_balance,
        final_equity=final_equity,
        total_return_pct=total_return,
        max_drawdown_pct=max_drawdown * 100,
        completed_trades=len(completed),
        winning_trades=len(winners),
        win_rate_pct=win_rate,
        trades=tuple(trades),
        equity_curve=tuple(equity_curve),
    )
