import csv
from datetime import datetime
from pathlib import Path
from typing import TextIO

from dataset import MarketDataset, from_candles
from market_data import Candle


REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")


class HistoricalDataError(ValueError):
    """Raised when a historical market-data file is invalid."""


def _parse_timestamp(value: str, row_number: int) -> datetime:
    try:
        timestamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise HistoricalDataError(
            f"invalid timestamp at row {row_number}"
        ) from exc

    if timestamp.tzinfo is None:
        raise HistoricalDataError(
            f"timestamp must be timezone-aware at row {row_number}"
        )
    return timestamp


def _parse_float(value: str, field: str, row_number: int) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise HistoricalDataError(
            f"invalid {field} at row {row_number}"
        ) from exc


def load_historical_csv(source: str | Path | TextIO) -> MarketDataset:
    """Load and validate OHLCV candles from a CSV file.

    Required columns: timestamp, open, high, low, close, volume.
    Timestamps must be timezone-aware and candles must be strictly ordered.
    """
    should_close = False
    if isinstance(source, (str, Path)):
        try:
            handle = open(source, "r", encoding="utf-8", newline="")
        except OSError as exc:
            raise HistoricalDataError(f"unable to read historical data: {exc}") from exc
        should_close = True
    else:
        handle = source

    try:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise HistoricalDataError("CSV is missing a header")

        columns = tuple(name.strip() for name in reader.fieldnames if name is not None)
        missing = [column for column in REQUIRED_COLUMNS if column not in columns]
        if missing:
            raise HistoricalDataError(
                f"CSV is missing required columns: {', '.join(missing)}"
            )

        candles: list[Candle] = []
        for row_number, row in enumerate(reader, start=2):
            try:
                candle = Candle(
                    timestamp=_parse_timestamp(row["timestamp"], row_number),
                    open=_parse_float(row["open"], "open", row_number),
                    high=_parse_float(row["high"], "high", row_number),
                    low=_parse_float(row["low"], "low", row_number),
                    close=_parse_float(row["close"], "close", row_number),
                    volume=_parse_float(row["volume"], "volume", row_number),
                )
            except KeyError as exc:
                raise HistoricalDataError(
                    f"missing required field {exc.args[0]!r} at row {row_number}"
                ) from exc
            candles.append(candle)

        if not candles:
            raise HistoricalDataError("CSV contains no candles")

        try:
            return from_candles(candles)
        except ValueError as exc:
            raise HistoricalDataError(str(exc)) from exc
    finally:
        if should_close:
            handle.close()
