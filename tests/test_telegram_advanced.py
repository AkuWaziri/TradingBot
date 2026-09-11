from dataclasses import dataclass

from telegram_advanced import CachedHeliusProvider, TelegramAdvancedReport, format_advanced_section


class FakeProvider:
    def __init__(self):
        self.signature_calls = []
        self.transaction_calls = []

    def get_recent_signatures(self, address, limit=100):
        self.signature_calls.append((address, limit))
        return [{"signature": "sig-1"}]

    def get_transaction(self, signature):
        self.transaction_calls.append(signature)
        return {"signature": signature}


@dataclass(frozen=True)
class FakeBundle:
    wallets_scanned: int = 4
    possible_related_groups: tuple = ()


@dataclass(frozen=True)
class FakeCreator:
    creator_wallet: str | None = "creator"
    creator_sells_observed: int = 1


@dataclass(frozen=True)
class FakeFlow:
    buyer_participation_growth_ratio: float | None = 2.0
    buy_flow_growth_ratio: float | None = 1.5
    unique_participants: int = 7
    unique_buyers: int = 4
    unique_sellers: int = 3


@dataclass(frozen=True)
class FakeManipulation:
    largest_trader_flow_share: float | None = 0.45
    warnings: tuple = ()


@dataclass(frozen=True)
class FakeIntelligence:
    bundle: FakeBundle = FakeBundle()
    creator: FakeCreator = FakeCreator()
    flow: FakeFlow = FakeFlow()
    manipulation: FakeManipulation = FakeManipulation()


def test_cached_provider_bounds_and_deduplicates_calls():
    raw = FakeProvider()
    provider = CachedHeliusProvider(raw, signature_limit=50)

    assert provider.get_recent_signatures("MINT", limit=100) == [{"signature": "sig-1"}]
    assert provider.get_recent_signatures("MINT", limit=50) == [{"signature": "sig-1"}]
    assert raw.signature_calls == [("MINT", 50)]

    provider.get_transaction("sig-1")
    provider.get_transaction("sig-1")
    assert raw.transaction_calls == ["sig-1"]


def test_advanced_section_contains_research_signals_and_warning_caveat():
    section = format_advanced_section(TelegramAdvancedReport(FakeIntelligence()))
    assert "🧠 ADVANCED RESEARCH" in section
    assert "Buyer growth: 2.00x" in section
    assert "Largest wallet flow: 45.0%" in section
    assert "Research heuristics only" in section
