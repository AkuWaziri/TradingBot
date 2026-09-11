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
        name="Test",
        price_usd=1.0,
        market_cap_usd=100_000,
        volume_24h_usd=50_000,
        price_change_24h_pct=10.0,
        liquidity_usd=30_000,
        created_at=NOW - timedelta(minutes=30),
        source="test",
    )


def make_pair(**changes):
    data = dict(
        chain_id="solana",
        dex_id="raydium",
        pair_address="PAIR",
        base_token_address=MINT,
        base_token_symbol="TEST",
        base_token_name="Test",
        quote_token_address="SOL",
        quote_token_symbol="SOL",
        price_usd=1.0,
        liquidity_usd=30_000,
        market_cap_usd=100_000,
        fdv_usd=100_000,
        price_change_5m_pct=5.0,
        price_change_1h_pct=10.0,
        price_change_6h_pct=15.0,
        price_change_24h_pct=20.0,
        volume_5m_usd=2_000,
        volume_1h_usd=8_000,
        volume_6h_usd=20_000,
        volume_24h_usd=50_000,
        buys_5m=20,
        sells_5m=10,
        buys_1h=80,
        sells_1h=40,
        buys_6h=200,
        sells_6h=100,
        buys_24h=500,
        sells_24h=250,
        pair_created_at=NOW - timedelta(minutes=30),
        url=None,
    )
    data.update(changes)
    return DexScreenerPair(**data)


def make_state(**changes):
    data = dict(
        mint=MINT,
        symbol="TEST",
        name="Test",
        supply_raw=1_000,
        decimals=0,
        token_program="spl-token",
        mint_authority=None,
        freeze_authority=None,
        price_usd=1.0,
        top_accounts=(
            TokenAccountShare("A", 100, 0, 100.0, "WalletA"),
            TokenAccountShare("B", 70, 0, 70.0, "WalletB"),
            TokenAccountShare("C", 50, 0, 50.0, "WalletC"),
            TokenAccountShare("D", 40, 0, 40.0, "WalletD"),
            TokenAccountShare("E", 30, 0, 30.0, "WalletE"),
        ),
        indexed_slot=123,
    )
    data.update(changes)
    return SolanaTokenState(**data)


def test_holder_concentration_aggregates_multiple_token_accounts_by_wallet():
    state = make_state()
    accounts = list(state.top_accounts)
    accounts[0] = TokenAccountShare("Account0", 150, 0, 150.0, "Wallet0")
    accounts[1] = TokenAccountShare("Account1", 100, 0, 100.0, "Wallet0")
    accounts[2] = TokenAccountShare("Account2", 100, 0, 100.0, "Wallet2")
    accounts[3] = TokenAccountShare("Account3", 50, 0, 50.0, "Wallet3")
    accounts[4] = TokenAccountShare("Account4", 50, 0, 50.0, "Wallet4")
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
        assert str(exc) == "holder owner resolution is unavailable"
    else:
        raise AssertionError("expected owner-resolution failure")
