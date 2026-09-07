from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True)
class Signal:
    action: str


def moving_average(values: Sequence[float], window: int) -> float:
    if window <= 0:
        raise ValueError("window must be positive")
    if len(values) < window:
        raise ValueError("not enough values for moving average")
    return sum(values[-window:]) / window


def generate_signal(prices: Sequence[float], fast_window: int, slow_window: int) -> Signal:
    if fast_window >= slow_window:
        raise ValueError("fast_window must be smaller than slow_window")
    if len(prices) < slow_window:
        return Signal("HOLD")

    fast = moving_average(prices, fast_window)
    slow = moving_average(prices, slow_window)

    if fast > slow:
        return Signal("BUY")
    if fast < slow:
        return Signal("SELL")
    return Signal("HOLD")
