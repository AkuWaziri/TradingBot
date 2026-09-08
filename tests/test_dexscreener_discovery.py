import dexscreener_market
from dexscreener_market import DexScreenerProvider


def test_latest_solana_token_addresses_filters_chain_and_deduplicates(monkeypatch):
    payload = [
        {"chainId": "ethereum", "tokenAddress": "ETH"},
        {"chainId": "solana", "tokenAddress": "MINT1"},
        {"chainId": "solana", "tokenAddress": "MINT1"},
        {"chainId": "solana", "tokenAddress": "MINT2"},
    ]
    monkeypatch.setattr(dexscreener_market, "_get_json", lambda *args, **kwargs: payload)

    addresses = DexScreenerProvider().latest_solana_token_addresses(limit=10)

    assert addresses == ["MINT1", "MINT2"]


def test_latest_solana_token_addresses_bounds_limit():
    provider = DexScreenerProvider()
    try:
        provider.latest_solana_token_addresses(limit=31)
    except ValueError as exc:
        assert str(exc) == "limit must be between 1 and 30"
    else:
        raise AssertionError("expected limit validation")
