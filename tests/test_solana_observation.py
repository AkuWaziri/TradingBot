from datetime import datetime, timezone

from dexscreener_market import DexScreenerPair
from live_market import LiveToken
from solana_observation import Observation, format_observations, select_best_pair


def pair(address: str, liquidity: float, volume: float) -> DexScreenerPair:
    now = datetime.now(timezone.utc)
    return DexScreenerPair(
        chain_id="solana", dex_id="raydium", pair_address=address,
        base_token_address="MINT", base_token_symbol="TEST", base_token_name="Test",
        quote_token_address="SOL", quote_token_symbol="SOL", price_usd=0.01,
        liquidity_usd=liquidity, market_cap_usd=1_000_000, fdv_usd=1_000_000,
        price_change_5m_pct=1, price_change_1h_pct=2, price_change_6h_pct=3,
        price_change_24h_pct=4, volume_5m_usd=volume, volume_1h_usd=volume * 2,
        volume_6h_usd=volume * 3, volume_24h_usd=volume * 4,
        buys_5m=10, sells_5m=5, buys_1h=20, sells_1h=10,
        buys_6h=30, sells_6h=15, buys_24h=40, sells_24h=20,
        pair_created_at=now, url=None,
    )


def test_select_best_pair_prefers_liquidity():
    selected = select_best_pair([pair("LOW", 20_000, 100_000), pair("HIGH", 50_000, 10_000)], "MINT")
    assert selected is not None
    assert selected.pair_address == "HIGH"


def test_select_best_pair_ignores_other_tokens():
    other = pair("OTHER", 999_999, 999_999)
    other = DexScreenerPair(**{**other.__dict__, "base_token_address": "OTHER_MINT"})
    assert select_best_pair([other], "MINT") is None


def test_format_observations_is_read_only():
    token = LiveToken("MINT", "TEST", "Test", None, None, None, None, None, None, "pump.fun")
    text = format_observations([Observation(token=token, pair=None, intelligence=None, error="no_solana_market_pair")])
    assert "read-only" in text
    assert "execution=disabled" in text
    assert "no_solana_market_pair" in text
