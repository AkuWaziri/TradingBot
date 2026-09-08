from datetime import datetime, timezone

import pytest

import live_runner
from live_market import LiveMarketError, LiveToken


def make_token() -> LiveToken:
    return LiveToken(
        mint="mint-1",
        symbol="TEST",
        name="Test",
        price_usd=None,
        market_cap_usd=100_000,
        volume_24h_usd=50_000,
        price_change_24h_pct=15,
        liquidity_usd=30_000,
        created_at=datetime.now(timezone.utc),
        source="pump.fun",
    )


def test_observation_fails_closed_when_coingecko_unavailable(monkeypatch):
    monkeypatch.setattr(live_runner.PumpFunProvider, "currently_live", lambda self, limit: [make_token()])

    def fail_enrich(self, tokens):
        raise LiveMarketError("provider unavailable")

    monkeypatch.setattr(live_runner.CoinGeckoProvider, "enrich", fail_enrich)

    output = live_runner.run_observation(limit=1)

    assert "execution=disabled" in output
    assert "coingecko=FAIL_CLOSED" in output
    assert "NO SIGNALS GENERATED" in output
    assert "BUY" not in output


def test_observation_reports_filter_reasons(monkeypatch):
    token = make_token()
    monkeypatch.setattr(live_runner.PumpFunProvider, "currently_live", lambda self, limit: [token])
    monkeypatch.setattr(live_runner.CoinGeckoProvider, "enrich", lambda self, tokens: tokens)

    output = live_runner.run_observation(limit=1)

    assert "REJECT TEST" in output
    assert "source=pump.fun" in output
    assert "missing valid price" in output


def test_observation_limit_is_bounded():
    with pytest.raises(ValueError, match="limit must be between 1 and 100"):
        live_runner.run_observation(limit=0)
