"""Read-only early-buyer intelligence for Solana token research.

This module identifies wallets that appear to have acquired a token early by
comparing parsed pre/post token balances with signer/native-balance movement.
It is intentionally conservative: transfers, airdrops, and incomplete parsed
transactions are not labeled as buys. No scoring, trading, signing, or order
execution occurs here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from helius_onchain import HeliusOnchainError, HeliusProvider


@dataclass(frozen=True)
class EarlyBuyer:
    wallet: str
    first_buy_slot: int
    first_buy_signature: str
    observed_buys: int
    token_amount_bought_raw: int
    native_spent_lamports: int

    def validate(self) -> None:
        if not self.wallet or self.first_buy_slot < 0 or not self.first_buy_signature:
            raise ValueError("invalid early buyer identity")
        if self.observed_buys <= 0:
            raise ValueError("observed_buys must be positive")
        if self.token_amount_bought_raw <= 0:
            raise ValueError("token amount bought must be positive")
        if self.native_spent_lamports <= 0:
            raise ValueError("native spend must be positive")


@dataclass(frozen=True)
class EarlyBuyerIntelligence:
    mint: str
    signatures_scanned: int
    transactions_parsed: int
    early_buyers: tuple[EarlyBuyer, ...]
    unique_early_buyers: int
    top_buyer_share_of_observed_buys: float | None
    incomplete_transactions: int

    def validate(self) -> None:
        if not self.mint:
            raise ValueError("mint is required")
        if self.signatures_scanned < 0 or self.transactions_parsed < 0:
            raise ValueError("scan counts cannot be negative")
        if self.unique_early_buyers != len(self.early_buyers):
            raise ValueError("unique early buyer count mismatch")
        if self.top_buyer_share_of_observed_buys is not None and not 0 <= self.top_buyer_share_of_observed_buys <= 1:
            raise ValueError("top buyer share must be between 0 and 1")


def _token_balance_delta(transaction: dict[str, Any], mint: str) -> dict[str, int]:
    meta = transaction.get("meta")
    if not isinstance(meta, dict):
        return {}
    pre = meta.get("preTokenBalances")
    post = meta.get("postTokenBalances")
    if not isinstance(pre, list) or not isinstance(post, list):
        return {}

    def aggregate(items: list[Any]) -> dict[str, int]:
        balances: dict[str, int] = {}
        for item in items:
            if not isinstance(item, dict) or str(item.get("mint") or "").strip() != mint:
                continue
            owner = str(item.get("owner") or "").strip()
            if not owner:
                continue
            raw = item.get("uiTokenAmount")
            if not isinstance(raw, dict):
                continue
            amount = raw.get("amount")
            try:
                amount_int = int(amount)
            except (TypeError, ValueError):
                continue
            if amount_int < 0:
                continue
            balances[owner] = balances.get(owner, 0) + amount_int
        return balances

    before = aggregate(pre)
    after = aggregate(post)
    owners = set(before) | set(after)
    return {owner: after.get(owner, 0) - before.get(owner, 0) for owner in owners}


def _signer_native_spend(transaction: dict[str, Any], wallet: str) -> int | None:
    message = transaction.get("transaction", {}).get("message", {})
    if not isinstance(message, dict):
        return None
    keys = message.get("accountKeys")
    meta = transaction.get("meta")
    if not isinstance(keys, list) or not isinstance(meta, dict):
        return None
    pre = meta.get("preBalances")
    post = meta.get("postBalances")
    if not isinstance(pre, list) or not isinstance(post, list) or len(pre) != len(post) or len(keys) != len(pre):
        return None

    for index, key in enumerate(keys):
        if isinstance(key, dict):
            pubkey = str(key.get("pubkey") or "").strip()
            signer = bool(key.get("signer"))
        else:
            pubkey = str(key).strip()
            signer = False
        if pubkey != wallet or not signer:
            continue
        try:
            delta = int(pre[index]) - int(post[index])
        except (TypeError, ValueError):
            return None
        return delta if delta > 0 else None
    return None


def _is_observed_buy(transaction: dict[str, Any], mint: str, signature: str) -> tuple[str, int, int] | None:
    deltas = _token_balance_delta(transaction, mint)
    if not deltas:
        return None
    candidates: list[tuple[str, int, int]] = []
    for wallet, token_delta in deltas.items():
        if token_delta <= 0:
            continue
        native_spend = _signer_native_spend(transaction, wallet)
        if native_spend is None:
            continue
        candidates.append((wallet, token_delta, native_spend))
    if len(candidates) != 1:
        # Ambiguous multi-wallet transactions are intentionally excluded rather
        # than assigning the same swap to multiple buyers.
        return None
    return candidates[0]


def inspect_early_buyers(
    mint: str,
    *,
    provider: HeliusProvider | None = None,
    signature_limit: int = 50,
    max_transactions: int = 30,
) -> EarlyBuyerIntelligence:
    """Inspect recent token-referencing transactions for conservative early buys."""
    mint = mint.strip()
    if not mint:
        raise ValueError("mint is required")
    if not 1 <= signature_limit <= 100:
        raise ValueError("signature_limit must be between 1 and 100")
    if not 1 <= max_transactions <= signature_limit:
        raise ValueError("max_transactions must be between 1 and signature_limit")

    provider = provider or HeliusProvider()
    signatures = provider.get_recent_signatures(mint, limit=signature_limit)
    aggregates: dict[str, dict[str, int | str]] = {}
    parsed = 0
    incomplete = 0

    # RPC signatures are newest-first. Reverse them so first_buy_slot reflects
    # the earliest observed buy in the scanned window.
    usable = [
        item for item in signatures
        if isinstance(item, dict) and item.get("err") is None and str(item.get("signature") or "").strip()
    ][:max_transactions]

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
        parsed += 1
        observed = _is_observed_buy(transaction, mint, signature)
        if observed is None:
            continue
        wallet, token_amount, native_spend = observed
        slot_raw = transaction.get("slot", item.get("slot"))
        try:
            slot = int(slot_raw)
        except (TypeError, ValueError):
            continue
        current = aggregates.setdefault(
            wallet,
            {
                "first_buy_slot": slot,
                "first_buy_signature": signature,
                "observed_buys": 0,
                "token_amount_bought_raw": 0,
                "native_spent_lamports": 0,
            },
        )
        current["first_buy_slot"] = min(int(current["first_buy_slot"]), slot)
        current["observed_buys"] = int(current["observed_buys"]) + 1
        current["token_amount_bought_raw"] = int(current["token_amount_bought_raw"]) + token_amount
        current["native_spent_lamports"] = int(current["native_spent_lamports"]) + native_spend

    buyers = []
    for wallet, data in aggregates.items():
        buyer = EarlyBuyer(
            wallet=wallet,
            first_buy_slot=int(data["first_buy_slot"]),
            first_buy_signature=str(data["first_buy_signature"]),
            observed_buys=int(data["observed_buys"]),
            token_amount_bought_raw=int(data["token_amount_bought_raw"]),
            native_spent_lamports=int(data["native_spent_lamports"]),
        )
        buyer.validate()
        buyers.append(buyer)

    buyers.sort(key=lambda buyer: (buyer.first_buy_slot, -buyer.native_spent_lamports, buyer.wallet))
    total_spend = sum(buyer.native_spent_lamports for buyer in buyers)
    top_share = buyers[0].native_spent_lamports / total_spend if buyers and total_spend > 0 else None

    result = EarlyBuyerIntelligence(
        mint=mint,
        signatures_scanned=len(signatures),
        transactions_parsed=parsed,
        early_buyers=tuple(buyers),
        unique_early_buyers=len(buyers),
        top_buyer_share_of_observed_buys=top_share,
        incomplete_transactions=incomplete,
    )
    result.validate()
    return result
