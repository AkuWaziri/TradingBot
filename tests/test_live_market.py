from datetime import datetime, timezone

import pytest

import live_market
from live_market import CoinGeckoProvider, LiveMarketError, LiveToken, PumpFunProvider


def test_live_token_rejects_non_positive_price():
    token = LiveToken(
        mint="mint-1",
        symbol="TEST",
        name="Test",
        price_usd=0,
        market_cap_usd=100_000,
        volume_24h_usd=10_000,
        price_change_24h_pct=5,
        liquidity_usd=25_000,
        created_at=datetime.now(timezone.utc),
        source="test",
    )
    with pytest.raises(ValueError, match="price_usd must be positive"):
        token.validate()


def test_pump_provider_requires_token():
    provider = PumpFunProvider(api_token="")
    with pytest.raises(LiveMarketError, match="PUMP_API_TOKEN is not configured"):
        provider.currently_live()


def test_pump_provider_parses_live_tokens(monkeypatch):
    payload = [
        {
            "mint": "mint-1",
            "symbol": "TEST",
            "name": "Test",
            "usd_market_cap": 100000,
            "volume_24h": 50000,
            "liquidity": 30000,
            "created_timestamp": 1757318400000,
        }
    ]

    monkeypatch.setattr(live_market, "_get_json", lambda *args, **kwargs: payload)
    tokens = PumpFunProvider(api_token="secret").currently_live(limit=1)

    assert len(tokens) == 1
    assert tokens[0].mint == "mint-1"
    assert tokens[0].price_usd is None
    assert tokens[0].market_cap_usd == 100000
    assert tokens[0].source == "pump.fun"


def test_coingecko_requires_key():
    provider = CoinGeckoProvider(api_key="")
    with pytest.raises(LiveMarketError, match="COINGECKO_API_KEY is not configured"):
        provider.prices_by_contracts(["mint-1"])


def test_coingecko_enriches_without_creating_false_fallbacks(monkeypatch):
    payload = {
        "mint-1": {
            "usd": 0.001,
            "usd_market_cap": 120000,
            "usd_24h_vol": 60000,
            "usd_24h_change": 18,
            "last_updated_at": 1757318400,
        }
    }
    monkeypatch.setattr(live_market, "_get_json", lambda *args, **kwargs: payload)

    token = LiveToken(
        mint="mint-1",
        symbol="TEST",
        name="Test",
        price_usd=None,
        market_cap_usd=100000,
        volume_24h_usd=50000,
        price_change_24h_pct=None,
        liquidity_usd=30000,
        created_at=datetime.now(timezone.utc),
        source="pump.fun",
    )

    enriched = CoinGeckoProvider(api_key="secret").enrich([token])[0]
    assert enriched.price_usd == 0.001
    assert enriched.market_cap_usd == 120000
    assert enriched.volume_24h_usd == 60000
    assert enriched.price_change_24h_pct == 18
    assert enriched.source == "pump.fun+coingecko"


def test_coingecko_keeps_pump_values_when_fields_are_absent(monkeypatch):
    monkeypatch.setattr(live_market, "_get_json", lambda *args, **kwargs: {})

    token = LiveToken(
        mint="mint-1",
        symbol="TEST",
        name="Test",
        price_usd=None,
        market_cap_usd=100000,
        volume_24h_usd=50000,
        price_change_24h_pct=12,
        liquidity_usd=30000,
        created_at=None,
        source="pump.fun",
    )

    enriched = CoinGeckoProvider(api_key="secret").enrich([token])[0]
    assert enriched.price_usd is None
    assert enriched.market_cap_usd == 100000
    assert enriched.volume_24h_usd == 50000
    assert enriched.price_change_24h_pct == 12
    assert enriched.source == "pump.fun"
