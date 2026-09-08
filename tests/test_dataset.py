from datetime import datetime, timedelta, timezone

import pytest

from dataset import from_candles, synthetic_dataset, validate_candles
from market_data import Candle


def candle(ts, open_price=100, high=105, low=95, close=102, volume=10):
    return Candle(ts, open_price, high, low, close, volume)


def test_dataset_exposes_closes_and_timestamps():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    data = from_candles([
        candle(start, close=102),
        candle(start + timedelta(minutes=1), open_price=102, high=108, low=101, close=107),
    ])
    assert data.closes == (102, 107)
    assert data.timestamps == (start, start + timedelta(minutes=1))


def test_candles_must_be_strictly_time_ordered():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="strictly increasing"):
        validate_candles([candle(start), candle(start)])


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        validate_candles([candle(datetime(2026, 1, 1))])


def test_invalid_ohlc_is_rejected():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="high"):
        validate_candles([candle(start, open_price=100, high=99, low=95, close=102)])


def test_synthetic_dataset_is_deterministic():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    data = synthetic_dataset([100, 105, 98], start=start, interval=timedelta(minutes=5), volume=25)
    assert data.closes == (100.0, 105.0, 98.0)
    assert data.candles[0].open == 100.0
    assert data.candles[1].open == 100.0
    assert data.candles[1].high == 105.0
    assert data.candles[1].low == 100.0
    assert data.candles[2].open == 105.0
    assert data.candles[2].high == 105.0
    assert data.candles[2].low == 98.0
    assert data.candles[2].timestamp == start + timedelta(minutes=10)


def test_synthetic_dataset_rejects_bad_input():
    with pytest.raises(ValueError):
        synthetic_dataset([])
    with pytest.raises(ValueError):
        synthetic_dataset([100, 0])
    with pytest.raises(ValueError):
        synthetic_dataset([100], interval=timedelta(0))
    with pytest.raises(ValueError):
        synthetic_dataset([100], volume=-1)
    with pytest.raises(ValueError, match="timezone-aware"):
        synthetic_dataset([100], start=datetime(2026, 1, 1))


def test_dataset_is_immutable():
    data = synthetic_dataset([100, 101])
    with pytest.raises(AttributeError):
        data.candles = ()
