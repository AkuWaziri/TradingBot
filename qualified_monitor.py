"""Read-only Solana monitor that emits only mature-qualified tokens."""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass

from advanced_intelligence import AdvancedIntelligence, inspect_advanced_intelligence
from advanced_qualification import AdvancedQualification, evaluate_advanced
from dexscreener_market import DexScreenerPair, DexScreenerProvider
from discovery import discover_candidates
from helius_onchain import HeliusProvider, HeliusOnchainError
from live_market import LiveMarketError, LiveToken
from qualification_engine import Qualification, Qualifier
from telegram_advanced import CachedHeliusProvider


@dataclass(frozen=True)
class Candidate:
    token: LiveToken
    pair: DexScreenerPair | None
    qualification: Qualification | None
    error: str | None = None


@dataclass(frozen=True)
class ScanResult:
    """Observable result of one read-only qualification scan."""

    requested: int
    discovered: int
    market_data_available: int
    evaluated: int
    qualified: tuple[Qualification, ...]
    rejection_reasons: tuple[tuple[str, int], ...]
    advanced_reports: tuple[tuple[str, AdvancedIntelligence, AdvancedQualification], ...] = ()


QUALIFICATION_CHECKS = (
    "liquidity_pass",
    "liquidity_ratio_pass",
    "recent_volume_pass",
    "buy_pressure_pass",
    "5m_momentum_pass",
    "1h_momentum_pass",
    "age_confirmation_pass",
    "authority_safety_pass",
)


def _pair_rank(pair: DexScreenerPair) -> tuple[float, float, float, int]:
    return (
        pair.liquidity_usd or 0.0,
        pair.volume_5m_usd or 0.0,
        (pair.buys_5m or 0) - (pair.sells_5m or 0),
        (pair.buys_5m or 0) + (pair.sells_5m or 0),
    )


def select_best_pair(pairs: list[DexScreenerPair], mint: str) -> DexScreenerPair | None:
    candidates = [p for p in pairs if p.chain_id == "solana" and p.base_token_address == mint]
    return max(candidates, key=_pair_rank, default=None)


def token_from_pair(pair: DexScreenerPair) -> LiveToken:
    token = LiveToken(
        mint=pair.base_token_address,
        symbol=pair.base_token_symbol,
        name=pair.base_token_name,
        price_usd=pair.price_usd,
        market_cap_usd=pair.market_cap_usd,
        volume_24h_usd=pair.volume_24h_usd,
        price_change_24h_pct=pair.price_change_24h_pct,
        liquidity_usd=pair.liquidity_usd,
        created_at=pair.pair_created_at,
        source="dexscreener",
    )
    token.validate()
    return token


def scan_tokens(limit: int = 30) -> ScanResult:
    """Run one read-only scan through core gates and advanced risk gates."""
    if not 1 <= limit <= 30:
        raise ValueError("limit must be between 1 and 30")

    dex = DexScreenerProvider()
    helius = HeliusProvider()
    qualifier = Qualifier()
    candidates = discover_candidates(limit=limit)
    mints = [item.mint for item in candidates]
    pairs = dex.pairs_by_tokens(mints)
    grouped: dict[str, list[DexScreenerPair]] = {}
    for pair in pairs:
        grouped.setdefault(pair.base_token_address, []).append(pair)

    qualified: list[Qualification] = []
    advanced_reports: list[tuple[str, AdvancedIntelligence, AdvancedQualification]] = []
    rejection_reasons: Counter[str] = Counter()
    market_data_available = 0
    evaluated = 0

    advanced_provider = CachedHeliusProvider(
        provider=helius,
        signature_limit=int(os.getenv("ADVANCED_QUALIFICATION_SIGNATURE_LIMIT", "40")),
    )
    advanced_max_transactions = int(os.getenv("ADVANCED_QUALIFICATION_MAX_TRANSACTIONS", "30"))

    for candidate in candidates:
        mint = candidate.mint
        pair = select_best_pair(grouped.get(mint, []), mint)
        if pair is None:
            try:
                pair = select_best_pair(dex.pairs_by_token(mint), mint)
            except (LiveMarketError, ValueError):
                pair = None
        if pair is None:
            rejection_reasons["market_data_unavailable"] += 1
            continue

        market_data_available += 1
        try:
            token = token_from_pair(pair)
            state = helius.inspect_token(mint)
            result = qualifier.evaluate(token, pair, state)
        except (HeliusOnchainError, LiveMarketError, ValueError) as exc:
            rejection_reasons[type(exc).__name__.lower()] += 1
            continue

        evaluated += 1
        if not result.qualified:
            if result.hard_flags:
                for reason in result.hard_flags:
                    rejection_reasons[reason] += 1
            else:
                rejection_reasons[f"score_below_{qualifier.minimum_score:.0f}"] += 1
            continue

        # Mature qualification is fail-closed: a core pass is not a final pass
        # until bounded transaction evidence and advanced risk gates also pass.
        try:
            signature_limit = advanced_provider._signature_limit
            intelligence = inspect_advanced_intelligence(
                mint,
                provider=advanced_provider,
                signature_limit=signature_limit,
                max_transactions=min(advanced_max_transactions, signature_limit),
            )
            advanced = evaluate_advanced(intelligence)
        except (HeliusOnchainError, LiveMarketError, ValueError) as exc:
            rejection_reasons["advanced_intelligence_unavailable"] += 1
            print(f"Advanced qualification unavailable for {mint}: {type(exc).__name__}: {exc}")
            continue

        if not advanced.qualified:
            for reason in advanced.hard_flags:
                rejection_reasons[reason] += 1
            continue

        qualified.append(result)
        advanced_reports.append((mint, intelligence, advanced))

    return ScanResult(
        requested=limit,
        discovered=len(candidates),
        market_data_available=market_data_available,
        evaluated=evaluated,
        qualified=tuple(qualified),
        rejection_reasons=tuple(rejection_reasons.most_common(12)),
        advanced_reports=tuple(advanced_reports),
    )


def find_qualified_tokens(limit: int = 30) -> list[Qualification]:
    """Compatibility wrapper returning only mature-qualified tokens."""
    return list(scan_tokens(limit=limit).qualified)


def _money(value: float) -> str:
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.0f}"


def format_telegram_alerts(qualified: list[Qualification]) -> str:
    """Format qualified tokens as compact, sectioned Telegram alerts."""
    if not qualified:
        return (
            "🔎 SOLANA QUALIFIED MONITOR\n"
            "────────────────────\n"
            "📭 No qualified tokens in this scan\n"
            "🛡️ Read-only · Manual trading only"
        )

    blocks = [
        "🟢 SOLANA QUALIFIED TOKENS",
        "────────────────────",
        "🛡️ READ-ONLY · MANUAL TRADING ONLY",
        f"🔎 {len(qualified)} token{'s' if len(qualified) != 1 else ''} qualified",
    ]

    for index, q in enumerate(sorted(qualified, key=lambda item: item.score, reverse=True), start=1):
        flow = "N/A" if q.buy_sell_ratio_5m is None else (
            "∞" if q.buy_sell_ratio_5m == float("inf") else f"{q.buy_sell_ratio_5m:.2f}"
        )
        passed = set(q.positives)
        failed = [check for check in QUALIFICATION_CHECKS if check not in passed]
        block = [
            f"\n#{index}  🟢 {q.symbol}  ·  {q.score:.0f}/100",
            "────────────────────",
            f"🧾 CA: {q.mint}",
            f"🏦 Venue: {q.dex_id}  ·  Age: {q.age_minutes:.1f}m",
            f"💰 Market: {_money(q.market_cap_usd)} MC  ·  {_money(q.liquidity_usd)} Liq",
            f"📈 Momentum: {q.price_change_5m_pct:+.2f}% (5m)  ·  {q.price_change_1h_pct:+.2f}% (1h)",
            f"⚡ Flow: {_money(q.volume_5m_usd)} 5m vol  ·  B/S {flow}",
            "✅ Passed: " + ", ".join(q.positives),
        ]
        if failed:
            block.append("⚠️ Failed: " + ", ".join(failed))
        if q.warnings:
            block.append("🚩 Warnings: " + ", ".join(q.warnings))
        blocks.append("\n".join(block))

    blocks.append("\n🔒 Execution: DISABLED")
    return "\n\n".join(blocks)


if __name__ == "__main__":
    print(format_telegram_alerts(find_qualified_tokens()))
