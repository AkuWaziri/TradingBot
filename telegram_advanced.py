"""Read-only advanced-intelligence enrichment for Telegram reports.

This module adds research context to already-qualified tokens. It never changes
qualification, signs transactions, or executes trades.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from advanced_intelligence import AdvancedIntelligence, inspect_advanced_intelligence
from helius_onchain import HeliusProvider


class CachedHeliusProvider:
    """Per-scan cache with a bounded signature window for Telegram."""

    def __init__(self, provider: HeliusProvider | None = None, signature_limit: int = 50) -> None:
        if signature_limit < 1:
            raise ValueError("signature_limit must be >= 1")
        self._provider = provider or HeliusProvider()
        self._signature_limit = signature_limit
        self._signatures: dict[tuple[str, int], list[dict[str, Any]]] = {}
        self._transactions: dict[str, dict[str, Any] | None] = {}

    def get_recent_signatures(self, address: str, limit: int = 100) -> list[dict[str, Any]]:
        bounded = min(limit, self._signature_limit)
        key = (address, bounded)
        if key not in self._signatures:
            self._signatures[key] = self._provider.get_recent_signatures(address, limit=bounded)
        return self._signatures[key]

    def get_transaction(self, signature: str) -> dict[str, Any] | None:
        if signature not in self._transactions:
            self._transactions[signature] = self._provider.get_transaction(signature)
        return self._transactions[signature]

    def __getattr__(self, name: str) -> Any:
        return getattr(self._provider, name)


@dataclass(frozen=True)
class TelegramAdvancedReport:
    intelligence: AdvancedIntelligence


def enrich_qualified(
    qualified: list[Any],
    *,
    limit: int = 5,
    signature_limit: int = 50,
    max_transactions: int = 40,
) -> dict[str, TelegramAdvancedReport]:
    """Enrich the highest-scoring qualified tokens without changing qualification."""
    if limit < 0:
        raise ValueError("limit must be >= 0")
    if signature_limit < 1 or max_transactions < 1:
        raise ValueError("signature_limit and max_transactions must be >= 1")

    provider = CachedHeliusProvider(signature_limit=signature_limit)
    reports: dict[str, TelegramAdvancedReport] = {}
    selected = sorted(qualified, key=lambda item: item.score, reverse=True)[:limit]
    for item in selected:
        intelligence = inspect_advanced_intelligence(
            item.mint,
            provider=provider,
            signature_limit=signature_limit,
            max_transactions=min(max_transactions, signature_limit),
        )
        reports[item.mint] = TelegramAdvancedReport(intelligence)
    return reports


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def _ratio(value: float | None) -> str:
    if value is None:
        return "N/A"
    if value == float("inf"):
        return "∞"
    return f"{value:.2f}x"


def format_advanced_section(report: TelegramAdvancedReport) -> str:
    intelligence = report.intelligence
    bundle = intelligence.bundle
    creator = intelligence.creator
    flow = intelligence.flow
    manipulation = intelligence.manipulation

    lines = [
        "🧠 ADVANCED RESEARCH",
        f"👥 Early buyers: {bundle.wallets_scanned}",
        f"🔗 Possible related groups: {len(bundle.possible_related_groups)}",
        f"📈 Buyer growth: {_ratio(flow.buyer_participation_growth_ratio)}",
        f"⚡ Buy-flow growth: {_ratio(flow.buy_flow_growth_ratio)}",
        f"👤 Participants: {flow.unique_participants} ({flow.unique_buyers} buyers / {flow.unique_sellers} sellers)",
        f"🧑‍💻 Creator: {creator.creator_wallet or 'not identified'}",
        f"📤 Creator sells observed: {creator.creator_sells_observed}",
    ]

    if manipulation.largest_trader_flow_share is not None:
        lines.append(f"💧 Largest wallet flow: {_pct(manipulation.largest_trader_flow_share)}")
    if manipulation.warnings:
        lines.append("🚩 Warnings: " + ", ".join(manipulation.warnings))
    else:
        lines.append("✅ Manipulation warnings: none")

    lines.append("ℹ️ Research heuristics only; not proof of coordination or safety")
    return "\n".join(lines)
