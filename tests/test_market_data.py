import json
from datetime import datetime, timezone
from urllib.error import URLError

import pytest

import market_data
from market_data import BinanceMarketData, Candle, MarketDataError


VALID_KLINE = [
    1_700_000_000_000,
    "100.0",
    "110.0",
    "95.0",
    "105.0",
    "123.45",
    1_700_000_059_999,
    "0",
    "0",
    "0",
    "0",
    "0",
]


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload


def test_parse_valid_kline():
    candles = BinanceMarketData._parse_klines([VALID_KLINE])

    assert candles == [
        Candle(
            timestamp=datetime.fromtimestamp(1_700_000_000, tz=timezone.utc),
            open=100.0,
            high=110.0,
            low=95.0,
            close=105.0,
            volume=123.45,
        )
    ]


def test_get_candles_builds_read_only_request(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["timeout"] = timeout
        return FakeResponse(json.dumps([VALID_KLINE]).encode())

    monkeypatch.setattr(market_data, "urlopen", fake_urlopen)

    candles = BinanceMarketData(timeout_seconds=7).get_candles("btcusdt", "1m", 25)

    assert len(candles) == 1
    assert "symbol=BTCUSDT" in captured["url"]
    assert "interval=1m" in captured["url"]
    assert "limit=25" in captured["url"]
    assert captured["method"] == "GET"
    assert captured["timeout"] == 7


def test_network_failure_is_wrapped(monkeypatch):
    def fake_urlopen(request, timeout):
        raise URLError("connection refused")

    monkeypatch.setattr(market_data, "urlopen", fake_urlopen)

    with pytest.raises(MarketDataError, match="market-data request failed"):
        BinanceMarketData().get_candles("BTCUSDT", "1m")


def test_invalid_json_is_rejected(monkeypatch):
    monkeypatch.setattr(
        market_data,
        "urlopen",
        lambda request, timeout: FakeResponse(b"not-json"),
    )

    with pytest.raises(MarketDataError, match="valid JSON"):
        BinanceMarketData().get_candles("BTCUSDT", "1m")


@pytest.mark.parametrize(
    "payload, message",
    [
        ({"error": "bad request"}, "must be a list"),
        ([[]], "invalid kline"),
        ([["bad", "100", "110", "95", "105", "1"]], "invalid numeric"),
        ([[1_700_000_000_000, "0", "110", "95", "105", "1"]], "non-positive price"),
        ([[1_700_000_000_000, "100", "90", "95", "105", "1"]], "invalid OHLC"),
        ([[1_700_000_000_000, "100", "110", "95", "105", "-1"]], "negative volume"),
    ],
)
def test_malformed_market_data_is_rejected(payload, message):
    with pytest.raises(MarketDataError, match=message):
        BinanceMarketData._parse_klines(payload)


@pytest.mark.parametrize(
    "symbol, interval, limit",
    [
        ("", "1m", 100),
        ("BTCUSDT", "", 100),
        ("BTCUSDT", "1m", 0),
        ("BTCUSDT", "1m", 1001),
        ("BTCUSDT", "1m", True),
    ],
)
def test_invalid_request_is_rejected(symbol, interval, limit):
    with pytest.raises(ValueError):
        BinanceMarketData().get_candles(symbol, interval, limit)


def test_base_url_must_use_https():
    with pytest.raises(ValueError, match="HTTPS"):
        BinanceMarketData("http://example.com")


def test_empty_payload_is_valid_but_contains_no_candles():
    assert BinanceMarketData._parse_klines([]) == []
