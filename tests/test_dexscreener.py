from datetime import datetime, timezone

import pytest

from dexscreener_market import DexScreenerProvider
from live_market import LiveMarketError


PAIR = {
    "chainId": "solana",
    "dexId": "raydium",
    "pairAddress": "PAIR111",
    "baseToken": {"address": "MINT111", "symbol": "TEST", "name": "Test"},
    "quoteToken": {"address": "SOL111", "symbol": "SOL", "name": "Solana"},
    "priceUsd": "0.0012",
    "liquidity": {"usd": 55000},
    "marketCap": 1200000,
    "fdv": 1500000,
    "priceChange": {"m5": 2.5, "h1": 8, "h6": 15, "h24": 31},
    "volume": {"m5": 1200, "h1": 15000, "h6": 70000, "h24": 180000},
    "txns": {
        "m5": {"buys": 12, "sells": 7},
        "h1": {"buys": 90, "sells": 61},
        "h6": {"buys": 410, "sells": 300},
        "h24": {"buys": 1200, "sells": 950},
    },
    "pairCreatedAt": 1788000000000,
    "url": "https://dexscreener.com/solana/PAIR111",
}


def test_bulk_sol_pairs_are_normalized(monkeypatch):
    monkeypatch.setattr(
        "dexscreener_market._get_json", lambda *args, **kwargs: [PAIR]
    )
    pairs = DexScreenerProvider().pairs_by_tokens(["MINT111"])
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair.chain_id == "solana"
    assert pair.base_token_address == "MINT111"
    assert pair.price_usd == 0.0012
    assert pair.liquidity_usd == 55000
    assert pair.buys_5m == 12
    assert pair.sells_24h == 950
    assert pair.pair_created_at.tzinfo == timezone.utc
    assert pair.url.endswith("PAIR111")


def test_non_solana_pairs_are_ignored(monkeypatch):
    payload = [{**PAIR, "chainId": "ethereum"}, PAIR]
    monkeypatch.setattr(
        "dexscreener_market._get_json", lambda *args, **kwargs: payload
    )
    pairs = DexScreenerProvider().pairs_by_tokens(["MINT111"])
    assert [pair.pair_address for pair in pairs] == ["PAIR111"]


def test_invalid_price_fails_closed(monkeypatch):
    payload = [{**PAIR, "priceUsd": -1}]
    monkeypatch.setattr(
        "dexscreener_market._get_json", lambda *args, **kwargs: payload
    )
    with pytest.raises(LiveMarketError, match="price_usd"):
        DexScreenerProvider().pairs_by_tokens(["MINT111"])


def test_malformed_transaction_count_fails_closed(monkeypatch):
    payload = [{
        **PAIR,
        "txns": {**PAIR["txns"], "m5": {"buys": "not-a-number", "sells": 1}},
    }]
    monkeypatch.setattr(
        "dexscreener_market._get_json", lambda *args, **kwargs: payload
    )
    with pytest.raises(LiveMarketError, match="transaction count"):
        DexScreenerProvider().pairs_by_tokens(["MINT111"])


def test_future_pair_timestamp_fails_closed(monkeypatch):
    future_ms = (datetime.now(timezone.utc).timestamp() + 3600) * 1000
    payload = [{**PAIR, "pairCreatedAt": future_ms}]
    monkeypatch.setattr(
        "dexscreener_market._get_json", lambda *args, **kwargs: payload
    )
    with pytest.raises(LiveMarketError, match="future"):
        DexScreenerProvider().pairs_by_tokens(["MINT111"])


def test_bulk_endpoint_limits_addresses(monkeypatch):
    with pytest.raises(ValueError, match="at most 30"):
        DexScreenerProvider().pairs_by_tokens([f"MINT{i}" for i in range(31)])


def test_single_token_endpoint(monkeypatch):
    monkeypatch.setattr(
        "dexscreener_market._get_json", lambda *args, **kwargs: [PAIR]
    )
    pairs = DexScreenerProvider().pairs_by_token("MINT111")
    assert len(pairs) == 1
