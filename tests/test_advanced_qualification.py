from advanced_intelligence import (
    AdvancedIntelligence,
    BundleIntelligence,
    CreatorIntelligence,
    FlowIntelligence,
    ManipulationIntelligence,
    RelatedWalletGroup,
)
from advanced_qualification import evaluate_advanced


def make_intelligence(**overrides):
    bundle = BundleIntelligence(
        wallets_scanned=12,
        possible_related_groups=(),
        wallets_in_related_groups=0,
        largest_group_share=0.0,
    )
    creator = CreatorIntelligence(
        creator_wallet="CREATOR",
        creation_signature="SIG",
        creation_slot=1,
        creator_buys_observed=0,
        creator_sells_observed=0,
        creator_sell_signatures=(),
        incomplete_transactions=0,
    )
    flow = FlowIntelligence(
        signatures_scanned=40,
        transactions_parsed=30,
        observed_buys=20,
        observed_sells=10,
        unique_buyers=16,
        unique_sellers=8,
        unique_participants=20,
        oldest_half_buy_count=8,
        newest_half_buy_count=12,
        oldest_half_sell_count=5,
        newest_half_sell_count=5,
        buyer_participation_growth_ratio=1.5,
        buy_flow_growth_ratio=1.5,
        incomplete_transactions=0,
    )
    manipulation = ManipulationIntelligence(
        observed_trades=30,
        unique_traders=20,
        largest_trader_trade_share=0.10,
        largest_trader_flow_share=0.20,
        repeated_trader_share=0.20,
        buy_sell_count_ratio=2.0,
        warnings=(),
    )
    values = dict(
        mint="MINT",
        bundle=bundle,
        creator=creator,
        flow=flow,
        manipulation=manipulation,
    )
    values.update(overrides)
    return AdvancedIntelligence(**values)


def test_clean_advanced_evidence_passes():
    result = evaluate_advanced(make_intelligence())

    assert result.qualified is True
    assert result.risk_level == "LOW"
    assert result.hard_flags == ()
    assert result.evidence_coverage == 1.0


def test_extreme_flow_concentration_is_hard_reject():
    manipulation = ManipulationIntelligence(
        observed_trades=30,
        unique_traders=20,
        largest_trader_trade_share=0.10,
        largest_trader_flow_share=0.75,
        repeated_trader_share=0.20,
        buy_sell_count_ratio=2.0,
        warnings=("single_wallet_flow_concentration",),
    )
    result = evaluate_advanced(make_intelligence(manipulation=manipulation))

    assert result.qualified is False
    assert "advanced_single_wallet_flow_concentration_too_high" in result.hard_flags


def test_possible_related_wallets_are_warning_below_hard_threshold():
    bundle = BundleIntelligence(
        wallets_scanned=20,
        possible_related_groups=(RelatedWalletGroup("FUNDER", ("A", "B"), "possible"),),
        wallets_in_related_groups=2,
        largest_group_share=0.10,
    )
    result = evaluate_advanced(make_intelligence(bundle=bundle))

    assert result.qualified is True
    assert result.risk_level == "MEDIUM"
    assert "advanced_possible_related_wallet_cluster" in result.warnings
    assert "advanced_possible_related_wallet_cluster_too_large" not in result.hard_flags


def test_insufficient_evidence_fails_closed():
    flow = FlowIntelligence(
        signatures_scanned=12,
        transactions_parsed=8,
        observed_buys=7,
        observed_sells=3,
        unique_buyers=5,
        unique_sellers=2,
        unique_participants=7,
        oldest_half_buy_count=3,
        newest_half_buy_count=4,
        oldest_half_sell_count=1,
        newest_half_sell_count=2,
        buyer_participation_growth_ratio=1.5,
        buy_flow_growth_ratio=1.5,
        incomplete_transactions=4,
    )
    manipulation = ManipulationIntelligence(
        observed_trades=10,
        unique_traders=7,
        largest_trader_trade_share=0.20,
        largest_trader_flow_share=0.25,
        repeated_trader_share=0.30,
        buy_sell_count_ratio=7 / 3,
        warnings=(),
    )
    result = evaluate_advanced(make_intelligence(flow=flow, manipulation=manipulation))

    assert result.qualified is False
    assert "advanced_evidence_window_too_small" in result.hard_flags
    assert "advanced_transaction_data_too_incomplete" in result.hard_flags
