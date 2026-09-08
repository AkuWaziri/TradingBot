from datetime import datetime, timezone

from live_market import LiveToken
from signal_engine import SignalConfig, score_token
from token_filter import FilterConfig, evaluate_token


def token(**overrides):
    values = dict(
        mint="mint-1",
        symbol="TEST",
        name="Test",
        price_usd=0.001,
        market_cap_usd=100_000,
        volume_24h_usd=50_000,
        price_change_24h_pct=15,
        liquidity_usd=50_000,
        created_at=datetime.now(timezone.utc),
        source="pump.fun+coingecko",
    )
    values.update(overrides)
    return LiveToken(**values)


def test_filter_accepts_valid_early_token():
    decision = evaluate_token(token(), FilterConfig())
    assert decision.accepted is True
    assert decision.reasons == ()


def test_filter_rejects_missing_price():
    decision = evaluate_token(token(price_usd=None), FilterConfig())
    assert decision.accepted is False
    assert "missing valid price" in decision.reasons


def test_filter_rejects_low_volume():
    decision = evaluate_token(token(volume_24h_usd=100), FilterConfig())
    assert decision.accepted is False
    assert "insufficient 24h volume" in decision.reasons


def test_signal_requires_evidence():
    signal = score_token(token(price_change_24h_pct=0, volume_24h_usd=1_000))
    assert signal.action == "HOLD"
    assert signal.score == 0


def test_signal_can_reach_buy_with_confirmations():
    signal = score_token(
        token(),
        fomo_activity_score=2,
        config=SignalConfig(buy_score=4, strong_buy_score=7),
    )
    assert signal.action == "STRONG_BUY"
    assert signal.score >= 7


def test_cross_source_divergence_fails_closed():
    signal = score_token(token(), pump_price_usd=0.0005)
    assert signal.action == "REJECT"
    assert "cross-source price divergence too high" in signal.reasons
