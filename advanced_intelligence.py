"""Read-only advanced Solana intelligence layers.

Layers in this module:
- possible related-wallet / common-funder detection
- creator/deployer behavior
- observed trading-flow and holder-participation growth
- deterministic manipulation / wash-trade warning signals

These are research signals, not trading decisions. They never sign, build, or
submit transactions and they do not modify the qualification score.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from early_buyer_intelligence import _is_observed_buy, _token_balance_delta
from helius_onchain import HeliusOnchainError, HeliusProvider


@dataclass(frozen=True)
class RelatedWalletGroup:
    funder: str
    wallets: tuple[str, ...]
    confidence: str


@dataclass(frozen=True)
class BundleIntelligence:
    wallets_scanned: int
    possible_related_groups: tuple[RelatedWalletGroup, ...]
    wallets_in_related_groups: int
    largest_group_share: float | None


@dataclass(frozen=True)
class CreatorIntelligence:
    creator_wallet: str | None
    creation_signature: str | None
    creation_slot: int | None
    creator_buys_observed: int
    creator_sells_observed: int
    creator_sell_signatures: tuple[str, ...]
    incomplete_transactions: int


@dataclass(frozen=True)
class FlowIntelligence:
    signatures_scanned: int
    transactions_parsed: int
    observed_buys: int
    observed_sells: int
    unique_buyers: int
    unique_sellers: int
    unique_participants: int
    oldest_half_buy_count: int
    newest_half_buy_count: int
    oldest_half_sell_count: int
    newest_half_sell_count: int
    buyer_participation_growth_ratio: float | None
    buy_flow_growth_ratio: float | None
    incomplete_transactions: int


@dataclass(frozen=True)
class ManipulationIntelligence:
    observed_trades: int
    unique_traders: int
    largest_trader_trade_share: float | None
    largest_trader_flow_share: float | None
    repeated_trader_share: float | None
    buy_sell_count_ratio: float | None
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class AdvancedIntelligence:
    mint: str
    bundle: BundleIntelligence
    creator: CreatorIntelligence
    flow: FlowIntelligence
    manipulation: ManipulationIntelligence


def _account_keys(transaction: dict[str, Any]) -> list[tuple[str, bool]]:
    message = transaction.get("transaction", {}).get("message", {})
    keys = message.get("accountKeys") if isinstance(message, dict) else None
    if not isinstance(keys, list):
        return []
    result: list[tuple[str, bool]] = []
    for key in keys:
        if isinstance(key, dict):
            pubkey = str(key.get("pubkey") or "").strip()
            signer = bool(key.get("signer"))
        else:
            pubkey = str(key).strip()
            signer = False
        if pubkey:
            result.append((pubkey, signer))
    return result


def _native_deltas(transaction: dict[str, Any]) -> dict[str, int]:
    meta = transaction.get("meta")
    if not isinstance(meta, dict):
        return {}
    pre = meta.get("preBalances")
    post = meta.get("postBalances")
    keys = _account_keys(transaction)
    if not isinstance(pre, list) or not isinstance(post, list) or len(pre) != len(post) or len(keys) != len(pre):
        return {}
    deltas: dict[str, int] = {}
    for index, (wallet, _) in enumerate(keys):
        try:
            delta = int(post[index]) - int(pre[index])
        except (TypeError, ValueError):
            continue
        deltas[wallet] = delta
    return deltas


def _single_signer(transaction: dict[str, Any]) -> str | None:
    signers = [wallet for wallet, signer in _account_keys(transaction) if signer]
    return signers[0] if len(signers) == 1 else None


def _observed_sell(transaction: dict[str, Any], mint: str) -> tuple[str, int, int] | None:
    deltas = _token_balance_delta(transaction, mint)
    native = _native_deltas(transaction)
    candidates: list[tuple[str, int, int]] = []
    for wallet, token_delta in deltas.items():
        if token_delta >= 0 or native.get(wallet, 0) <= 0:
            continue
        if not any(pubkey == wallet and signer for pubkey, signer in _account_keys(transaction)):
            continue
        candidates.append((wallet, -token_delta, native[wallet]))
    return candidates[0] if len(candidates) == 1 else None


def _find_prior_funding_source(
    wallet: str,
    first_buy_signature: str,
    *,
    provider: HeliusProvider,
) -> str | None:
    """Return a possible immediate funding source, never claiming certainty."""
    try:
        signatures = provider.get_recent_signatures(wallet, limit=20)
    except HeliusOnchainError:
        return None
    target_index = next(
        (index for index, item in enumerate(signatures) if str(item.get("signature") or "") == first_buy_signature),
        None,
    )
    if target_index is None or target_index + 1 >= len(signatures):
        return None
    prior_signature = str(signatures[target_index + 1].get("signature") or "").strip()
    if not prior_signature:
        return None
    try:
        transaction = provider.get_transaction(prior_signature)
    except HeliusOnchainError:
        return None
    if transaction is None:
        return None
    deltas = _native_deltas(transaction)
    if deltas.get(wallet, 0) <= 0:
        return None
    candidates = [source for source, delta in deltas.items() if source != wallet and delta < 0]
    return candidates[0] if len(candidates) == 1 else None


def inspect_related_wallets(
    mint: str,
    *,
    early_buyers: list[Any],
    provider: HeliusProvider | None = None,
) -> BundleIntelligence:
    provider = provider or HeliusProvider()
    funding: dict[str, list[str]] = {}
    for buyer in early_buyers:
        source = _find_prior_funding_source(buyer.wallet, buyer.first_buy_signature, provider=provider)
        if source:
            funding.setdefault(source, []).append(buyer.wallet)

    groups: list[RelatedWalletGroup] = []
    for source, wallets in funding.items():
        unique_wallets = tuple(sorted(set(wallets)))
        if len(unique_wallets) < 2:
            continue
        groups.append(RelatedWalletGroup(source, unique_wallets, "possible"))
    groups.sort(key=lambda group: (-len(group.wallets), group.funder))
    wallet_count = len({wallet for group in groups for wallet in group.wallets})
    largest_share = None
    if early_buyers:
        largest_share = max((len(group.wallets) for group in groups), default=0) / len(early_buyers)
    return BundleIntelligence(
        wallets_scanned=len(early_buyers),
        possible_related_groups=tuple(groups),
        wallets_in_related_groups=wallet_count,
        largest_group_share=largest_share,
    )


def _creation_transaction(mint: str, provider: HeliusProvider) -> tuple[str | None, dict[str, Any] | None]:
    try:
        signatures = provider.get_recent_signatures(mint, limit=1000)
    except HeliusOnchainError:
        return None, None
    usable = [
        item for item in signatures
        if isinstance(item, dict) and item.get("err") is None and str(item.get("signature") or "").strip()
    ]
    for item in reversed(usable):
        signature = str(item["signature"]).strip()
        try:
            transaction = provider.get_transaction(signature)
        except HeliusOnchainError:
            continue
        if transaction is not None:
            return signature, transaction
    return None, None


def inspect_creator_behavior(
    mint: str,
    *,
    provider: HeliusProvider | None = None,
    signature_limit: int = 100,
) -> CreatorIntelligence:
    provider = provider or HeliusProvider()
    creation_signature, creation_tx = _creation_transaction(mint, provider)
    if creation_tx is None:
        return CreatorIntelligence(None, None, None, 0, 0, (), 1)

    creator = _single_signer(creation_tx)
    slot_raw = creation_tx.get("slot")
    try:
        slot = int(slot_raw)
    except (TypeError, ValueError):
        slot = None

    try:
        signatures = provider.get_recent_signatures(mint, limit=signature_limit)
    except HeliusOnchainError:
        return CreatorIntelligence(creator, creation_signature, slot, 0, 0, (), 1)

    buys = sells = incomplete = 0
    sell_signatures: list[str] = []
    for item in signatures:
        signature = str(item.get("signature") or "").strip() if isinstance(item, dict) else ""
        if not signature or (isinstance(item, dict) and item.get("err") is not None):
            continue
        try:
            transaction = provider.get_transaction(signature)
        except HeliusOnchainError:
            incomplete += 1
            continue
        if transaction is None:
            incomplete += 1
            continue
        observed_buy = _is_observed_buy(transaction, mint, signature)
        if observed_buy is not None and observed_buy[0] == creator:
            buys += 1
        observed_sell = _observed_sell(transaction, mint)
        if observed_sell is not None and observed_sell[0] == creator:
            sells += 1
            sell_signatures.append(signature)

    return CreatorIntelligence(
        creator,
        creation_signature,
        slot,
        buys,
        sells,
        tuple(sell_signatures[:20]),
        incomplete,
    )


def inspect_flow(
    mint: str,
    *,
    provider: HeliusProvider | None = None,
    signature_limit: int = 100,
    max_transactions: int = 80,
) -> FlowIntelligence:
    provider = provider or HeliusProvider()
    signatures = provider.get_recent_signatures(mint, limit=signature_limit)
    usable = [
        item for item in signatures
        if isinstance(item, dict) and item.get("err") is None and str(item.get("signature") or "").strip()
    ][:max_transactions]

    events: list[tuple[int, str, str]] = []
    incomplete = 0
    for item in reversed(usable):
        signature = str(item["signature"]).strip()
        try:
            transaction = provider.get_transaction(signature)
        except HeliusOnchainError:
            incomplete += 1
            continue
        if transaction is None:
            incomplete += 1
            continue
        slot_raw = transaction.get("slot", item.get("slot"))
        try:
            slot = int(slot_raw)
        except (TypeError, ValueError):
            continue
        buy = _is_observed_buy(transaction, mint, signature)
        if buy is not None:
            events.append((slot, "buy", buy[0]))
            continue
        sell = _observed_sell(transaction, mint)
        if sell is not None:
            events.append((slot, "sell", sell[0]))

    midpoint = len(events) // 2
    oldest = events[:midpoint]
    newest = events[midpoint:]
    buyers = {wallet for _, kind, wallet in events if kind == "buy"}
    sellers = {wallet for _, kind, wallet in events if kind == "sell"}
    oldest_buyers = {wallet for _, kind, wallet in oldest if kind == "buy"}
    newest_buyers = {wallet for _, kind, wallet in newest if kind == "buy"}
    oldest_buy_count = sum(1 for _, kind, _ in oldest if kind == "buy")
    newest_buy_count = sum(1 for _, kind, _ in newest if kind == "buy")
    oldest_sell_count = sum(1 for _, kind, _ in oldest if kind == "sell")
    newest_sell_count = sum(1 for _, kind, _ in newest if kind == "sell")

    participation_ratio = None
    if oldest_buyers:
        participation_ratio = len(newest_buyers) / len(oldest_buyers)
    flow_ratio = None
    if oldest_buy_count:
        flow_ratio = newest_buy_count / oldest_buy_count

    return FlowIntelligence(
        signatures_scanned=len(signatures),
        transactions_parsed=len(usable) - incomplete,
        observed_buys=sum(1 for _, kind, _ in events if kind == "buy"),
        observed_sells=sum(1 for _, kind, _ in events if kind == "sell"),
        unique_buyers=len(buyers),
        unique_sellers=len(sellers),
        unique_participants=len(buyers | sellers),
        oldest_half_buy_count=oldest_buy_count,
        newest_half_buy_count=newest_buy_count,
        oldest_half_sell_count=oldest_sell_count,
        newest_half_sell_count=newest_sell_count,
        buyer_participation_growth_ratio=participation_ratio,
        buy_flow_growth_ratio=flow_ratio,
        incomplete_transactions=incomplete,
    )


def inspect_manipulation(
    mint: str,
    *,
    provider: HeliusProvider | None = None,
    signature_limit: int = 100,
    max_transactions: int = 80,
) -> ManipulationIntelligence:
    provider = provider or HeliusProvider()
    signatures = provider.get_recent_signatures(mint, limit=signature_limit)
    usable = [
        item for item in signatures
        if isinstance(item, dict) and item.get("err") is None and str(item.get("signature") or "").strip()
    ][:max_transactions]

    trades: list[tuple[str, str, int]] = []
    for item in usable:
        signature = str(item["signature"]).strip()
        try:
            transaction = provider.get_transaction(signature)
        except HeliusOnchainError:
            continue
        if transaction is None:
            continue
        buy = _is_observed_buy(transaction, mint, signature)
        if buy is not None:
            trades.append((buy[0], "buy", buy[2]))
            continue
        sell = _observed_sell(transaction, mint)
        if sell is not None:
            trades.append((sell[0], "sell", sell[2]))

    total_flow = sum(amount for _, _, amount in trades)
    wallet_trade_counts: dict[str, int] = {}
    wallet_flow: dict[str, int] = {}
    for wallet, _, amount in trades:
        wallet_trade_counts[wallet] = wallet_trade_counts.get(wallet, 0) + 1
        wallet_flow[wallet] = wallet_flow.get(wallet, 0) + amount

    observed = len(trades)
    largest_trade_share = max(wallet_trade_counts.values(), default=0) / observed if observed else None
    largest_flow_share = max(wallet_flow.values(), default=0) / total_flow if total_flow else None
    repeated_share = sum(count for count in wallet_trade_counts.values() if count > 1) / observed if observed else None
    buys = sum(1 for _, kind, _ in trades if kind == "buy")
    sells = sum(1 for _, kind, _ in trades if kind == "sell")
    ratio = buys / sells if sells else (float("inf") if buys else None)

    warnings: list[str] = []
    if largest_trade_share is not None and largest_trade_share >= 0.50:
        warnings.append("single_wallet_trade_concentration")
    if largest_flow_share is not None and largest_flow_share >= 0.50:
        warnings.append("single_wallet_flow_concentration")
    if repeated_share is not None and repeated_share >= 0.60:
        warnings.append("high_repeated_wallet_activity")
    if buys >= 10 and sells == 0:
        warnings.append("one_sided_observed_flow")
    if observed >= 10 and len(wallet_trade_counts) <= 3:
        warnings.append("low_unique_trader_diversity")

    return ManipulationIntelligence(
        observed_trades=observed,
        unique_traders=len(wallet_trade_counts),
        largest_trader_trade_share=largest_trade_share,
        largest_trader_flow_share=largest_flow_share,
        repeated_trader_share=repeated_share,
        buy_sell_count_ratio=ratio,
        warnings=tuple(warnings),
    )


def inspect_advanced_intelligence(
    mint: str,
    *,
    provider: HeliusProvider | None = None,
    signature_limit: int = 100,
    max_transactions: int = 80,
) -> AdvancedIntelligence:
    provider = provider or HeliusProvider()
    from early_buyer_intelligence import inspect_early_buyers

    early = inspect_early_buyers(
        mint,
        provider=provider,
        signature_limit=min(signature_limit, 100),
        max_transactions=min(max_transactions, signature_limit),
    )
    bundle = inspect_related_wallets(mint, early_buyers=list(early.early_buyers), provider=provider)
    creator = inspect_creator_behavior(mint, provider=provider, signature_limit=signature_limit)
    flow = inspect_flow(mint, provider=provider, signature_limit=signature_limit, max_transactions=max_transactions)
    manipulation = inspect_manipulation(mint, provider=provider, signature_limit=signature_limit, max_transactions=max_transactions)
    return AdvancedIntelligence(mint, bundle, creator, flow, manipulation)
