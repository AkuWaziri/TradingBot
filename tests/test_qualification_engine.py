from datetime import datetime, timedelta, timezone

from dexscreener_market import DexScreenerPair
from helius_onchain import SolanaTokenState, TokenAccountShare
from live_market import LiveToken
from qualification_engine import Qualifier
from solana_intelligence import build_onchain_features


NOW = datetime(2026, 9, 11, 10, 0, tzinfo=timezone.utc)
MINT = "So11111111111111111111111111111111111111112"


def make_token() -> LiveToken:
    return LiveToken(
        mint=MINT,
        symbol="TEST",
        name="Test Token",
        price_usd=1.0,
        market_cap_usd=100_000.0,
        volume_24h_usd=100_000.0,
        price_change_24h_pct=10.0,
        liquidity_usd=30_000.0,
        created_at=NOW - timedelta(minutes=30),
        source="test",
    )


def make_pair(price_change_5m: float, price_change_1h: float = 20.0) -> DexScreenerPair:
    return DexScreenerPair(
        chain_id="solana",
        dex_id="raydium",
        pair_address="Pair111111111111111111111111111111111111111",
        base_token_address=MINT,
        base_token_symbol="TEST",
        base_token_name="Test Token",
        quote_token_address="USDC111111111111111111111111111111111111111",
        quote_token_symbol="USDC",
        price_usd=1.0,
        liquidity_usd=30_000.0,
        market_cap_usd=100_000.0,
        fdv_usd=100_000.0,
        price_change_5m_pct=price_change_5m,
        price_change_1h_pct=price_change_1h,
        price_change_6h_pct=30.0,
        price_change_24h_pct=40.0,
        volume_5m_usd=5_000.0,
        volume_1h_usd=20_000.0,
        volume_6h_usd=50_000.0,
        volume_24h_usd=100_000.0,
        buys_5m=137,
        sells_5m=100,
        buys_1h=200,
        sells_1h=100,
        buys_6h=400,
        sells_6h=200,
        buys_24h=800,
        sells_24h=400,
        pair_created_at=NOW - timedelta(minutes=30),
        url=None,
    )


def make_state() -> SolanaTokenState:
    return SolanaTokenState(
        mint=MINT,
        symbol="TEST",
        name="Test Token",
        supply_raw=1_000,
        decimals=0,
        token_program="spl-token",
        mint_authority=None,
        freeze_authority=None,
        price_usd=1.0,
        top_accounts=tuple(
            TokenAccountShare(
                address=f"Account{i}",
                raw_amount=50,
                decimals=0,
                ui_amount=50.0,
                owner=f"Wallet{i}",
            )
            for i in range(5)
        ),
        indexed_slot=123,
    )


def test_strong_token_can_score_100():
    result = Qualifier().evaluate(make_token(), make_pair(10.0), make_state(), now=NOW)

    assert result.qualified is True
    assert result.score == 100.0
    assert result.hard_flags == ()


def test_extreme_5m_selloff_is_rejected_even_when_other_checks_pass():
    result = Qualifier().evaluate(make_token(), make_pair(-20.78), make_state(), now=NOW)

    assert result.qualified is False
    assert result.score == 0.0
    assert "extreme_negative_5m_momentum" in result.hard_flags


def test_normal_negative_5m_momentum_remains_score_based():
    result = Qualifier().evaluate(make_token(), make_pair(-5.0), make_state(), now=NOW)

    assert result.qualified is True
    assert result.score == 87.5
    assert "negative_5m_momentum" in result.warnings


def test_holder_concentration_aggregates_multiple_token_accounts_by_wallet():
    state = make_state()
    accounts = list(state.top_accounts)
    accounts[0] = TokenAccountShare("Account0", 150, 0, 150.0, "Wallet0")
    accounts[1] = TokenAccountShare("Account1", 100, 0, 100.0, "Wallet0")
    state = SolanaTokenState(
        mint=state.mint,
        symbol=state.symbol,
        name=state.name,
        supply_raw=state.supply_raw,
        decimals=state.decimals,
        token_program=state.token_program,
        mint_authority=state.mint_authority,
        freeze_authority=state.freeze_authority,
        price_usd=state.price_usd,
        top_accounts=tuple(accounts),
        indexed_slot=state.indexed_slot,
    )

    features = build_onchain_features(state)

    assert features.top_account_share == 0.25
    assert features.top_5_account_share == 0.45


def test_holder_concentration_requires_owner_resolution():
    state = make_state()
    accounts = list(state.top_accounts)
    accounts[0] = TokenAccountShare("Account0", 50, 0, 50.0)
    state = SolanaTokenState(
        mint=state.mint,
        symbol=state.symbol,
        name=state.name,
        supply_raw=state.supply_raw,
        decimals=state.decimals,
        token_program=state.token_program,
        mint_authority=state.mint_authority,
        freeze_authority=state.freeze_authority,
        price_usd=state.price_usd,
        top_accounts=tuple(accounts),
        indexed_slot=state.indexed_slot,
    )

    try:
        build_onchain_features(state)
    except ValueError as exc:
        assert "owner resolution" in str(exc)
    else:
        raise AssertionError("owner resolution must be required")
