import pytest

from helius_onchain import HeliusOnchainError, HeliusProvider


ASSET = {
    "last_indexed_slot": 123456,
    "content": {"metadata": {"symbol": "TEST", "name": "Test Token"}},
    "token_info": {
        "supply": 1_000_000_000,
        "decimals": 6,
        "token_program": "TokenkegQfeZyiNwAJYbNbGKPFXCWuBvf9Ss623VQ5DA",
        "mint_authority": None,
        "freeze_authority": None,
        "price_info": {"price_per_token": 0.0012, "currency": "USD"},
    },
}

LARGEST = {
    "value": [
        {"address": "ACCOUNT1", "amount": "500000000", "decimals": 6, "uiAmount": 500},
        {"address": "ACCOUNT2", "amount": "100000000", "decimals": 6, "uiAmount": 100},
    ]
}

OWNERS = {
    "value": [
        {
            "data": {
                "parsed": {
                    "info": {"mint": "MINT1", "owner": "WALLET1"}
                }
            }
        },
        {
            "data": {
                "parsed": {
                    "info": {"mint": "MINT1", "owner": "WALLET2"}
                }
            }
        },
    ]
}


def test_inspect_token_normalizes_onchain_state(monkeypatch):
    provider = HeliusProvider(api_key="test")

    def fake_rpc(method, params):
        if method == "getAsset":
            return ASSET
        if method == "getTokenLargestAccounts":
            return LARGEST
        if method == "getMultipleAccounts":
            return OWNERS
        raise AssertionError(method)

    monkeypatch.setattr(provider, "_rpc", fake_rpc)
    state = provider.inspect_token("MINT1")
    assert state.symbol == "TEST"
    assert state.supply_raw == 1_000_000_000
    assert state.decimals == 6
    assert state.mint_authority is None
    assert state.freeze_authority is None
    assert len(state.top_accounts) == 2
    assert state.top_accounts[0].raw_amount == 500_000_000
    assert state.top_accounts[0].owner == "WALLET1"
    assert state.top_accounts[1].owner == "WALLET2"


def test_get_asset_requires_mint():
    provider = HeliusProvider(api_key="test")
    with pytest.raises(ValueError, match="mint"):
        provider.get_asset(" ")


def test_missing_api_key_fails_closed():
    provider = HeliusProvider(api_key=None)
    with pytest.raises(HeliusOnchainError, match="HELIUS_API_KEY"):
        provider.get_asset("MINT1")


def test_rpc_error_fails_closed(monkeypatch):
    provider = HeliusProvider(api_key="test")
    monkeypatch.setattr(
        "helius_onchain.urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network should not run")),
    )
    monkeypatch.setattr(provider, "api_key", "test")
    monkeypatch.setattr(provider, "_rpc", lambda *args: (_ for _ in ()).throw(HeliusOnchainError("Helius RPC error")))
    with pytest.raises(HeliusOnchainError, match="RPC error"):
        provider.get_asset("MINT1")


def test_invalid_largest_account_fails_closed(monkeypatch):
    provider = HeliusProvider(api_key="test")
    monkeypatch.setattr(
        provider,
        "_rpc",
        lambda method, params: {"value": [{"address": "A", "amount": "bad", "decimals": 6}]},
    )
    with pytest.raises(HeliusOnchainError, match="amount"):
        provider.get_largest_accounts("MINT1")


def test_supply_fallback(monkeypatch):
    provider = HeliusProvider(api_key="test")
    calls = []

    def fake_rpc(method, params):
        calls.append(method)
        if method == "getAsset":
            return {"last_indexed_slot": 1, "content": {"metadata": {}}, "token_info": {}}
        if method == "getTokenSupply":
            return {"value": {"amount": "1000", "decimals": 3}}
        if method == "getTokenLargestAccounts":
            return {"value": []}
        raise AssertionError(method)

    monkeypatch.setattr(provider, "_rpc", fake_rpc)
    state = provider.inspect_token("MINT1")
    assert state.supply_raw == 1000
    assert state.decimals == 3
    assert calls == ["getAsset", "getTokenSupply", "getTokenLargestAccounts"]
