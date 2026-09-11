from advanced_intelligence import (
    _native_deltas,
    _observed_sell,
    inspect_creator_behavior,
    inspect_flow,
    inspect_manipulation,
    inspect_related_wallets,
)

MINT = "MINT111"


def tx(signature, slot, wallet, token_before, token_after, native_before, native_after, extra=None):
    keys = [{"pubkey": wallet, "signer": True}]
    pre_balances = [native_before]
    post_balances = [native_after]
    pre_tokens = [{"mint": MINT, "owner": wallet, "uiTokenAmount": {"amount": str(token_before)}}]
    post_tokens = [{"mint": MINT, "owner": wallet, "uiTokenAmount": {"amount": str(token_after)}}]
    if extra:
        keys.extend(extra[0])
        pre_balances.extend(extra[1])
        post_balances.extend(extra[2])
        pre_tokens.extend(extra[3])
        post_tokens.extend(extra[4])
    return {
        "slot": slot,
        "transaction": {"message": {"accountKeys": keys}},
        "meta": {
            "preBalances": pre_balances,
            "postBalances": post_balances,
            "preTokenBalances": pre_tokens,
            "postTokenBalances": post_tokens,
        },
    }


class FakeProvider:
    def __init__(self):
        self.transactions = {
            "CREATE": tx("CREATE", 10, "CREATOR", 0, 0, 10_000, 9_900),
            "BUY1": tx("BUY1", 20, "W1", 0, 100, 5_000, 4_000),
            "BUY2": tx("BUY2", 30, "W2", 0, 100, 5_000, 4_000),
            "SELL1": tx("SELL1", 40, "W1", 100, 50, 4_000, 4_500),
            "BUY3": tx("BUY3", 50, "W1", 50, 150, 4_500, 3_500),
        }
        self.signatures = {
            MINT: [
                {"signature": "BUY3", "slot": 50, "err": None},
                {"signature": "SELL1", "slot": 40, "err": None},
                {"signature": "BUY2", "slot": 30, "err": None},
                {"signature": "BUY1", "slot": 20, "err": None},
                {"signature": "CREATE", "slot": 10, "err": None},
            ],
            "W1": [
                {"signature": "BUY3", "slot": 50, "err": None},
                {"signature": "SELL1", "slot": 40, "err": None},
                {"signature": "BUY1", "slot": 20, "err": None},
                {"signature": "FUND1", "slot": 15, "err": None},
            ],
            "W2": [
                {"signature": "BUY2", "slot": 30, "err": None},
                {"signature": "FUND2", "slot": 25, "err": None},
            ],
        }
        self.transactions["FUND1"] = tx("FUND1", 15, "FUNDER", 0, 0, 10_000, 8_000, extra=([
            {"pubkey": "W1", "signer": False}
        ], [0], [2_000], [], []))
        self.transactions["FUND2"] = tx("FUND2", 25, "FUNDER", 0, 0, 8_000, 6_000, extra=([
            {"pubkey": "W2", "signer": False}
        ], [0], [2_000], [], []))

    def get_recent_signatures(self, address, limit):
        return self.signatures.get(address, [])[:limit]

    def get_transaction(self, signature):
        return self.transactions.get(signature)


def test_native_deltas():
    result = _native_deltas(FakeProvider().transactions["BUY1"])
    assert result["W1"] == -1000


def test_sell_is_detected():
    result = _observed_sell(FakeProvider().transactions["SELL1"], MINT)
    assert result == ("W1", 50, 500)


def test_related_wallets_share_possible_funder():
    provider = FakeProvider()
    buyers = [
        type("Buyer", (), {"wallet": "W1", "first_buy_signature": "BUY1"})(),
        type("Buyer", (), {"wallet": "W2", "first_buy_signature": "BUY2"})(),
    ]
    result = inspect_related_wallets(MINT, early_buyers=buyers, provider=provider)
    assert result.wallets_in_related_groups == 2
    assert result.possible_related_groups[0].funder == "FUNDER"


def test_creator_is_first_observed_signer_and_sell_is_tracked():
    provider = FakeProvider()
    result = inspect_creator_behavior(MINT, provider=provider, signature_limit=10)
    assert result.creator_wallet == "CREATOR"
    assert result.creation_signature == "CREATE"
    assert result.creator_sells_observed == 0


def test_flow_measures_participation_and_direction():
    result = inspect_flow(MINT, provider=FakeProvider(), signature_limit=10, max_transactions=5)
    assert result.observed_buys == 3
    assert result.observed_sells == 1
    assert result.unique_buyers == 2
    assert result.unique_sellers == 1


def test_manipulation_flags_repeated_wallet_activity_when_dominant():
    result = inspect_manipulation(MINT, provider=FakeProvider(), signature_limit=10, max_transactions=5)
    assert result.observed_trades == 4
    assert result.unique_traders == 2
    assert result.repeated_trader_share is not None
    assert "high_repeated_wallet_activity" in result.warnings
