from io import StringIO

import pytest

from historical import HistoricalDataError, load_historical_csv


VALID_CSV = """timestamp,open,high,low,close,volume
2026-01-01T00:00:00+00:00,100,105,95,102,10
2026-01-01T00:01:00+00:00,102,108,101,107,12
"""


def test_load_historical_csv_parses_candles():
    data = load_historical_csv(StringIO(VALID_CSV))
    assert data.closes == (102.0, 107.0)
    assert data.candles[1].volume == 12.0


def test_loader_accepts_zulu_timestamps():
    data = load_historical_csv(
        StringIO(
            "timestamp,open,high,low,close,volume\n"
            "2026-01-01T00:00:00Z,100,100,100,100,1\n"
        )
    )
    assert data.candles[0].timestamp.isoformat() == "2026-01-01T00:00:00+00:00"


def test_missing_columns_are_rejected():
    with pytest.raises(HistoricalDataError, match="missing required columns"):
        load_historical_csv(StringIO("timestamp,open,close\n2026-01-01T00:00:00+00:00,100,101\n"))


def test_bad_number_is_rejected():
    csv = VALID_CSV.replace(",102,10", ",not-a-number,10")
    with pytest.raises(HistoricalDataError, match="invalid close"):
        load_historical_csv(StringIO(csv))


def test_naive_timestamp_is_rejected():
    csv = VALID_CSV.replace("2026-01-01T00:00:00+00:00", "2026-01-01T00:00:00")
    with pytest.raises(HistoricalDataError, match="timezone-aware"):
        load_historical_csv(StringIO(csv))


def test_invalid_ohlc_is_rejected():
    csv = VALID_CSV.replace(",105,95,102,10", ",99,95,102,10")
    with pytest.raises(HistoricalDataError, match="high is below"):
        load_historical_csv(StringIO(csv))


def test_out_of_order_rows_are_rejected():
    csv = """timestamp,open,high,low,close,volume
2026-01-01T00:01:00+00:00,100,105,95,102,10
2026-01-01T00:00:00+00:00,102,108,101,107,12
"""
    with pytest.raises(HistoricalDataError, match="strictly increasing"):
        load_historical_csv(StringIO(csv))


def test_empty_csv_is_rejected():
    with pytest.raises(HistoricalDataError, match="no candles"):
        load_historical_csv(StringIO("timestamp,open,high,low,close,volume\n"))
