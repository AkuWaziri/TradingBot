from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Sequence

from market_data import Candle


@dataclass(frozen=True)
class MarketDataset:
    """Validated, ordered market data suitable for deterministic backtests."""

    candles: tuple[Candle, ...]

    def __post_init__(self) -> None:
        validate_candles(self.candles)

    @property
    def closes(self) -> tuple[float, ...]:
        return tuple(candle.close for candle in self.candles)

    @property
    def timestamps(self) -> tuple[datetime, ...]:
        return tuple(candle.timestamp for candle in self.candles)


def validate_candles(candles: Sequence[Candle]) -> None:
    if not candles:
        raise ValueError("candles must not be empty")

    previous_timestamp: datetime | None = None
    for index, candle in enumerate(candles):
        if not isinstance(candle, Candle):
            raise ValueError(f"invalid candle at index {index}")
        if candle.timestamp.tzinfo is None:
            raise ValueError(f"candle timestamp must be timezone-aware at index {index}")
        if any(not isfinite(value) or value <= 0 for value in (candle.open, candle.high, candle.low, candle.close)):
            raise ValueError(f"invalid price at index {index}")
        if not isfinite(candle.volume) or candle.volume < 0:
            raise ValueError(f"invalid volume at index {index}")
        if candle.high < max(candle.open, candle.close):
            raise ValueError(f"high is below open/close at index {index}")
        if candle.low > min(candle.open, candle.close):
            raise ValueError(f"low is above open/close at index {index}")
        if previous_timestamp is not None and candle.timestamp <= previous_timestamp:
            raise ValueError("candles must be strictly increasing by timestamp")
        previous_timestamp = candle.timestamp


def from_candles(candles: Sequence[Candle]) -> MarketDataset:
    return MarketDataset(tuple(candles))


def synthetic_dataset(
    closes: Sequence[float],
    *,
    start: datetime | None = None,
    interval: timedelta = timedelta(minutes=1),
    volume: float = 1.0,
) -> MarketDataset:
    """Build deterministic OHLCV candles from a close-price sequence."""
    if not closes:
        raise ValueError("closes must not be empty")
    if interval <= timedelta(0):
        raise ValueError("interval must be positive")
    if not isfinite(volume) or volume < 0:
        raise ValueError("volume must be finite and non-negative")

    start = start or datetime(2020, 1, 1, tzinfo=timezone.utc)
    if start.tzinfo is None:
        raise ValueError("start must be timezone-aware")

    previous_close = None
    candles: list[Candle] = []
    for index, raw_close in enumerate(closes):
        close = float(raw_close)
        if not isfinite(close) or close <= 0:
            raise ValueError(f"close must be positive and finite at index {index}")
        open_price = close if previous_close is None else previous_close
        candles.append(Candle(start + index * interval, open_price, max(open_price, close), min(open_price, close), close, volume))
        previous_close = close

    return MarketDataset(tuple(candles))
