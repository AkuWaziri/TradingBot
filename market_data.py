from dataclasses import dataclass
from datetime import datetime, timezone
from json import JSONDecodeError, loads
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class Candle:
    """A single OHLCV market-data point."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketDataError(RuntimeError):
    """Raised when market data cannot be fetched or validated."""


class MarketData(Protocol):
    def get_candles(self, symbol: str, interval: str, limit: int = 100) -> list[Candle]:
        """Return validated candles in exchange response order."""


class BinanceMarketData:
    """Read-only market-data adapter for Binance public spot klines.

    No API key or account credentials are required. This adapter only reads
    public market data and does not place orders.
    """

    DEFAULT_BASE_URL = "https://api.binance.com"
    KLINES_PATH = "/api/v3/klines"
    DEFAULT_TIMEOUT_SECONDS = 10.0
    MAX_LIMIT = 1000

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not base_url.startswith("https://"):
            raise ValueError("base_url must use HTTPS")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def get_candles(self, symbol: str, interval: str, limit: int = 100) -> list[Candle]:
        self._validate_request(symbol, interval, limit)

        query = urlencode(
            {
                "symbol": symbol.upper(),
                "interval": interval,
                "limit": limit,
            }
        )
        url = f"{self.base_url}{self.KLINES_PATH}?{query}"
        request = Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "TradingBot/1.0"},
            method="GET",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = response.read()
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise MarketDataError(f"market-data request failed: {exc}") from exc

        try:
            raw_candles = loads(payload)
        except (JSONDecodeError, TypeError) as exc:
            raise MarketDataError("market-data response was not valid JSON") from exc

        return self._parse_klines(raw_candles)

    @staticmethod
    def _validate_request(symbol: str, interval: str, limit: int) -> None:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        if not isinstance(interval, str) or not interval.strip():
            raise ValueError("interval must be a non-empty string")
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValueError("limit must be an integer")
        if not 1 <= limit <= BinanceMarketData.MAX_LIMIT:
            raise ValueError(
                f"limit must be between 1 and {BinanceMarketData.MAX_LIMIT}"
            )

    @staticmethod
    def _parse_klines(payload: object) -> list[Candle]:
        if not isinstance(payload, list):
            raise MarketDataError("market-data response must be a list")

        candles: list[Candle] = []
        for index, row in enumerate(payload):
            if not isinstance(row, list) or len(row) < 6:
                raise MarketDataError(f"invalid kline at index {index}")

            try:
                timestamp_ms = int(row[0])
                open_price = float(row[1])
                high_price = float(row[2])
                low_price = float(row[3])
                close_price = float(row[4])
                volume = float(row[5])
            except (TypeError, ValueError, OverflowError) as exc:
                raise MarketDataError(f"invalid numeric kline at index {index}") from exc

            if timestamp_ms < 0:
                raise MarketDataError(f"invalid timestamp at index {index}")
            if any(value <= 0 for value in (open_price, high_price, low_price, close_price)):
                raise MarketDataError(f"non-positive price at index {index}")
            if volume < 0:
                raise MarketDataError(f"negative volume at index {index}")
            if high_price < max(open_price, close_price) or low_price > min(open_price, close_price):
                raise MarketDataError(f"invalid OHLC relationship at index {index}")

            candles.append(
                Candle(
                    timestamp=datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc),
                    open=open_price,
                    high=high_price,
                    low=low_price,
                    close=close_price,
                    volume=volume,
                )
            )

        return candles
