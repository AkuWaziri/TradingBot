from datetime import datetime, timezone, timedelta

import pytest

from dexscreener_market import DexScreenerPair
from helius_onchain import SolanaTokenState, TokenAccountShare
from live_market import LiveToken
from solana_intelligence import (
    IntelligenceConfig,
    build_market_features,
    build_onchain_features,
    evaluate_token,
)


NOW = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)


def make_token():
    return LiveToken(
        mint="MINT111",
        symbol="TEST",
        name="Test",
        price_usd=0.0012,
        market_cap_usd=1_200_000,
        volume_24h_usd=180_000,
        price_change_24h_pct=31,
        liquidity_usd=55_000,
        created_at=NOW - timedelta(minutes=30),
        source="pump.fun",
    )


def make_pair(**changes):
    data = dict(
        chain_id="solana",
        dex_id="raydium",
        pair_address="PAIR111",
        base_token_address="MINT111",
        base_token_symbol="TEST",
        base_token_name="Test",
        quote_token_address="SOL111",
        quote_token_symbol="SOL",
        price_usd=0.0012,
        liquidity_usd=55_000,
        market_cap_usd=1_200_000,
        fdv_usd=1_500_000,
        price_change_5m_pct=2.5,
        price_change_1h_pct=8,
        price_change_6h_pct=15,
        price_change_24h_pct=31,
        volume_5m_usd=1_200,
        volume_1h_usd=15_000,
        volume_6h_usd=70_000,
        volume_24h_usd=180_000,
        buys_5m=12,
        sells_5m=7,
        buys_1h=90,
        sells_1h=61,
        buys_6h=410,
        sells_6h=300,
        buys_24h=1200,
        sells_24h=950,
        pair_created_at=NOW - timedelta(minutes=30),
        url=None,
    )
    data.update(changes)
    return DexScreenerPair(**data)


def make_state(**changes):
    data = dict(
        mint="MINT111",
        symbol="TEST",
        name="Test",
        supply_raw=1_000_000,
        decimals=0,
        token_program="TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
        mint_authority=None,
        freeze_authority=None,
        price_usd=0.0012,
        top_accounts=(
            TokenAccountShare("A", 100_000, 0, 100_000, "WalletA"),
            TokenAccountShare("B", 70_000, 0, 70_000, "WalletB"),
            TokenAccountShare("C", 50_000, 0, 50_000, "WalletC"),
            TokenAccountShare("D", 40_000, 0, 40_000, "WalletD"),
            TokenAccountShare("E", 30_000, 0, 30_000, "WalletE"),
        ),
        indexed_slot=123,
    )
    data.update(changes)
    return SolanaTokenState(**data)


def test_market_features_are_deterministic():
    features = build_market_features(make_pair(), now=NOW)
    assert features.age_minutes == 30
    assert features.buy_sell_ratio_5m == pytest.approx(12 / 7)
    assert features.liquidity_to_mcap == pytest.approx(55_000 / 1_200_000)
    assert features.volume_5m_to_mcap == pytest.approx(1_200 / 1_200_000)


def test_onchain_concentration_uses_wallet_owners():
    features = build_onchain_features(make_state())
    assert features.top_account_share == pytest.approx(0.10)
    assert features.top_5_account_share == pytest.approx(0.29)
    assert features.top_20_account_share == pytest.approx(0.29)
    assert features.mint_authority_present is False


def test_strong_complete_setup_reaches_buy():
    result = evaluate_token(make_token(), make_pair(), make_state(), now=NOW)
    assert result.decision == "BUY"
    assert result.hard_risk_flags == ()
    assert result.confidence == 1.0


def test_mint_authority_is_hard_reject():
    result = evaluate_token(
        make_token(),
        make_pair(),
        make_state(mint_authority="AUTHORITY"),
        now=NOW,
    )
    assert result.decision == "REJECT"
    assert "mint_authority_present" in result.hard_risk_flags


def test_freeze_authority_is_hard_reject():
    result = evaluate_token(
        make_token(),
        make_pair(),
        make_state(freeze_authority="AUTHORITY"),
        now=NOW,
    )
    assert result.decision == "REJECT"
    assert "freeze_authority_present" in result.hard_risk_flags


def test_weak_recent_flow_does_not_buy():
    result = evaluate_token(
        make_token(),
        make_pair(buys_5m=4, sells_5m=20, price_change_5m_pct=-3),
        make_state(),
        now=NOW,
    )
    assert result.decision in {"WATCH", "NO_TRADE"}
    assert result.decision != "BUY"
    assert "weak_buy_pressure" in result.warnings


def test_too_new_pair_is_not_immediate_buy():
    result = evaluate_token(
        make_token(),
        make_pair(pair_created_at=NOW - timedelta(seconds=30)),
        make_state(),
        now=NOW,
    )
    assert result.decision != "BUY"
    assert "too_new_for_confirmation" in result.warnings


def test_missing_market_data_fails_closed():
    result = evaluate_token(
        make_token(),
        make_pair(liquidity_usd=None),
        make_state(),
        now=NOW,
    )
    assert result.decision == "REJECT"
    assert "missing_or_invalid_liquidity" in result.hard_risk_flags


def test_identity_mismatch_is_rejected():
    result = evaluate_token(
        make_token(),
        make_pair(base_token_address="OTHER"),
        make_state(),
        now=NOW,
    )
    assert result.decision == "REJECT"
    assert "mint_identity_mismatch" in result.hard_risk_flags
