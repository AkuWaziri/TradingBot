from early_buyer_intelligence import (
    _is_observed_buy,
    _signer_native_spend,
    _token_balance_delta,
    inspect_early_buyers,
)


MINT = "MINT111"


def make_transaction(signature="SIG1", slot=100, wallet="WALLET1", token_before=0, token_after=500, native_before=10_000, native_after=9_000):
    return {
        "slot": slot,
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": wallet, "signer": True},
                    {"pubkey": "OTHER", "signer": False},
                ]
            }
        },
        "meta": {
            "preBalances": [native_before, 0],
            "postBalances": [native_after, 0],
            "preTokenBalances": [
                {"mint": MINT, "owner": wallet, "uiTokenAmount": {"amount": str(token_before)}}
            ],
            "postTokenBalances": [
                {"mint": MINT, "owner": wallet, "uiTokenAmount": {"amount": str(token_after)}}
            ],
        },
    }


def test_token_balance_delta_is_wallet_based():
    transaction = make_transaction()
    assert _token_balance_delta(transaction, MINT) == {"WALLET1": 500}


def test_signer_native_spend_is_detected():
    transaction = make_transaction(native_before=10_000, native_after=8_500)
    assert _signer_native_spend(transaction, "WALLET1") == 1_500


def test_observed_buy_requires_token_increase_and_native_spend():
    transaction = make_transaction()
    assert _is_observed_buy(transaction, MINT, "SIG1") == ("WALLET1", 500, 1_000)


def test_transfer_without_signer_spend_is_not_a_buy():
    transaction = make_transaction(native_before=10_000, native_after=10_000)
    assert _is_observed_buy(transaction, MINT, "SIG1") is None


def test_ambiguous_multi_wallet_buy_is_excluded():
    transaction = make_transaction()
    transaction["meta"]["preTokenBalances"].append(
        {"mint": MINT, "owner": "WALLET2", "uiTokenAmount": {"amount": "0"}}
    )
    transaction["meta"]["postTokenBalances"].append(
        {"mint": MINT, "owner": "WALLET2", "uiTokenAmount": {"amount": "200"}}
    )
    transaction["transaction"]["message"]["accountKeys"].append(
        {"pubkey": "WALLET2", "signer": True}
    )
    transaction["meta"]["preBalances"].append(5_000)
    transaction["meta"]["postBalances"].append(4_500)
    assert _is_observed_buy(transaction, MINT, "SIG1") is None


def test_inspect_early_buyers_aggregates_and_orders(monkeypatch):
    class FakeProvider:
        def get_recent_signatures(self, mint, limit):
            return [
                {"signature": "SIG200", "slot": 200, "err": None},
                {"signature": "SIG100", "slot": 100, "err": None},
            ]

        def get_transaction(self, signature):
            if signature == "SIG100":
                return make_transaction(signature, 100, "WALLET1", 0, 500, 10_000, 9_000)
            return make_transaction(signature, 200, "WALLET1", 500, 900, 9_000, 8_000)

    result = inspect_early_buyers(MINT, provider=FakeProvider(), signature_limit=2, max_transactions=2)

    assert result.signatures_scanned == 2
    assert result.transactions_parsed == 2
    assert result.unique_early_buyers == 1
    assert result.early_buyers[0].wallet == "WALLET1"
    assert result.early_buyers[0].first_buy_slot == 100
    assert result.early_buyers[0].observed_buys == 2
    assert result.early_buyers[0].token_amount_bought_raw == 900
    assert result.early_buyers[0].native_spent_lamports == 2_000
    assert result.top_buyer_share_of_observed_buys == 1.0
