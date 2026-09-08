import argparse
from pathlib import Path

from backtest import run_backtest
from config import config
from historical import load_historical_csv
from performance import calculate_performance, format_report


def run_historical_backtest(
    source: str | Path,
    *,
    initial_balance: float | None = None,
    fast_window: int | None = None,
    slow_window: int | None = None,
    max_position_pct: float | None = None,
    fee_rate: float = 0.0,
) -> str:
    """Run the configured strategy against a validated historical CSV."""
    dataset = load_historical_csv(source)
    prices = dataset.closes

    balance = config.initial_balance if initial_balance is None else initial_balance
    fast = config.fast_window if fast_window is None else fast_window
    slow = config.slow_window if slow_window is None else slow_window
    position_pct = (
        config.max_position_pct if max_position_pct is None else max_position_pct
    )

    result = run_backtest(
        prices,
        initial_balance=balance,
        fast_window=fast,
        slow_window=slow,
        max_position_pct=position_pct,
        fee_rate=fee_rate,
    )

    first_close = prices[0]
    last_close = prices[-1]
    buy_and_hold_return_pct = (last_close - first_close) / first_close * 100
    report = calculate_performance(
        result,
        buy_and_hold_return_pct=buy_and_hold_return_pct,
    )

    return format_report(report)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a historical TradingBot backtest")
    parser.add_argument("csv", help="Path to an OHLCV CSV file")
    parser.add_argument("--fee-rate", type=float, default=0.0)
    args = parser.parse_args()

    print(run_historical_backtest(args.csv, fee_rate=args.fee_rate))


if __name__ == "__main__":
    main()
