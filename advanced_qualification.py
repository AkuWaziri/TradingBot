"""Deterministic advanced-risk qualification for read-only Solana screening.

The core qualification engine answers whether market/on-chain basics are strong.
This layer answers whether there is enough transaction evidence to trust that
result and whether the observed behavior contains strong structural red flags.

Signals described only as heuristics remain warnings unless their evidence is
strong enough for a conservative hard gate. Nothing here signs, trades, or
changes execution state.
"""

from __future__ import annotations

from dataclasses import dataclass

from advanced_intelligence import AdvancedIntelligence


@dataclass(frozen=True)
class AdvancedQualificationConfig:
    """Conservative production defaults; tune only from measured observations."""

    min_signatures_scanned: int = 20
    min_observed_trades: int = 10
    min_unique_participants: int = 5
    max_incomplete_transaction_ratio: float = 0.20
    hard_largest_trade_share: float = 0.70
    hard_largest_flow_share: float = 0.70
    hard_repeated_trader_share: float = 0.70
    hard_related_group_share: float = 0.25
    hard_related_group_min_wallets: int = 3
    hard_one_sided_buy_count: int = 15
    hard_low_diversity_trade_count: int = 15
    hard_low_diversity_unique_traders: int = 3


@dataclass(frozen=True)
class AdvancedQualification:
    qualified: bool
    risk_level: str
    hard_flags: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence_coverage: float


def evaluate_advanced(
    intelligence: AdvancedIntelligence,
    *,
    config: AdvancedQualificationConfig | None = None,
) -> AdvancedQualification:
    """Apply conservative, deterministic advanced gates to observed evidence."""
    config = config or AdvancedQualificationConfig()
    hard: list[str] = []
    warnings: list[str] = []

    flow = intelligence.flow
    manipulation = intelligence.manipulation
    bundle = intelligence.bundle
    creator = intelligence.creator

    signatures_ok = flow.signatures_scanned >= config.min_signatures_scanned
    trades_ok = manipulation.observed_trades >= config.min_observed_trades
    participants_ok = flow.unique_participants >= config.min_unique_participants
    denominator = max(flow.transactions_parsed + flow.incomplete_transactions, 1)
    incomplete_ratio = flow.incomplete_transactions / denominator
    completeness_ok = incomplete_ratio <= config.max_incomplete_transaction_ratio

    evidence_checks = (signatures_ok, trades_ok, participants_ok, completeness_ok)
    evidence_coverage = sum(evidence_checks) / len(evidence_checks)

    if not signatures_ok:
        hard.append("advanced_evidence_window_too_small")
    if not trades_ok:
        hard.append("advanced_observed_trade_count_too_small")
    if not participants_ok:
        hard.append("advanced_participant_count_too_small")
    if not completeness_ok:
        hard.append("advanced_transaction_data_too_incomplete")

    if manipulation.largest_trader_trade_share is not None:
        if manipulation.largest_trader_trade_share >= config.hard_largest_trade_share:
            hard.append("advanced_single_wallet_trade_concentration_too_high")
        elif manipulation.largest_trader_trade_share >= 0.50:
            warnings.append("advanced_single_wallet_trade_concentration")

    if manipulation.largest_trader_flow_share is not None:
        if manipulation.largest_trader_flow_share >= config.hard_largest_flow_share:
            hard.append("advanced_single_wallet_flow_concentration_too_high")
        elif manipulation.largest_trader_flow_share >= 0.50:
            warnings.append("advanced_single_wallet_flow_concentration")

    if manipulation.repeated_trader_share is not None:
        if manipulation.repeated_trader_share >= config.hard_repeated_trader_share:
            hard.append("advanced_repeated_wallet_activity_too_high")
        elif manipulation.repeated_trader_share >= 0.60:
            warnings.append("advanced_high_repeated_wallet_activity")

    if (
        manipulation.observed_trades >= config.hard_low_diversity_trade_count
        and manipulation.unique_traders <= config.hard_low_diversity_unique_traders
    ):
        hard.append("advanced_low_unique_trader_diversity")

    if flow.observed_buys >= config.hard_one_sided_buy_count and flow.observed_sells == 0:
        hard.append("advanced_one_sided_observed_flow")

    if (
        bundle.largest_group_share is not None
        and bundle.largest_group_share >= config.hard_related_group_share
        and bundle.wallets_in_related_groups >= config.hard_related_group_min_wallets
    ):
        hard.append("advanced_possible_related_wallet_cluster_too_large")
    elif bundle.possible_related_groups:
        warnings.append("advanced_possible_related_wallet_cluster")

    if creator.creator_sells_observed > 0:
        warnings.append("advanced_creator_sell_observed")

    if flow.buyer_participation_growth_ratio is not None and flow.buyer_participation_growth_ratio < 1.0:
        warnings.append("advanced_buyer_participation_not_growing")
    if flow.buy_flow_growth_ratio is not None and flow.buy_flow_growth_ratio < 1.0:
        warnings.append("advanced_buy_flow_not_growing")

    for warning in manipulation.warnings:
        if warning not in warnings:
            warnings.append(f"advanced_{warning}")

    if hard:
        risk_level = "HIGH"
    elif warnings:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"

    return AdvancedQualification(
        qualified=not hard,
        risk_level=risk_level,
        hard_flags=tuple(dict.fromkeys(hard)),
        warnings=tuple(dict.fromkeys(warnings)),
        evidence_coverage=round(evidence_coverage, 2),
    )
