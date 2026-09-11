"""Read-only Solana monitor that emits only qualified tokens."""

from __future__ import annotations

from dataclasses import dataclass

from dexscreener_market import DexScreenerPair, DexScreenerProvider
from helius_onchain import HeliusProvider, HeliusOnchainError
from live_market import LiveMarketError, LiveToken
from qualification_engine import Qualification, Qualifier


@dataclass(frozen=True)
class Candidate:
    token: LiveToken
    pair: DexScreenerPair | None
    qualification: Qualification | None
    error: str | None = None


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


def find_qualified_tokens(limit: int = 30) -> list[Qualification]:
    if not 1 <= limit <= 30:
        raise ValueError("limit must be between 1 and 30")

    dex = DexScreenerProvider()
    helius = HeliusProvider()
    qualifier = Qualifier()
    mints = dex.latest_solana_token_addresses(limit=limit)
    pairs = dex.pairs_by_tokens(mints)
    grouped: dict[str, list[DexScreenerPair]] = {}
    for pair in pairs:
        grouped.setdefault(pair.base_token_address, []).append(pair)

    qualified: list[Qualification] = []
    for mint in mints:
        pair = select_best_pair(grouped.get(mint, []), mint)
        if pair is None:
            continue
        try:
            token = token_from_pair(pair)
            state = helius.inspect_token(mint)
            result = qualifier.evaluate(token, pair, state)
        except (HeliusOnchainError, LiveMarketError, ValueError):
            continue
        if result.qualified:
            qualified.append(result)
    return qualified


def _money(value: float) -> str:
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.0f}"


def format_telegram_alerts(qualified: list[Qualification]) -> str:
    if not qualified:
        return "SOLANA QUALIFIED MONITOR\nNo qualified tokens in this scan.\n\nMANUAL TRADING ONLY"

    blocks = ["SOLANA QUALIFIED TOKENS", "manual trading only — no automated execution"]
    for q in sorted(qualified, key=lambda item: item.score, reverse=True):
        flow = "N/A" if q.buy_sell_ratio_5m is None else ("∞" if q.buy_sell_ratio_5m == float("inf") else f"{q.buy_sell_ratio_5m:.2f}")
        passed = set(q.positives)
        failed = [check for check in QUALIFICATION_CHECKS if check not in passed]
        lines = [
            f"🟢 {q.symbol} — {q.score:.0f}/100",
            f"CA: {q.mint}",
            f"DEX: {q.dex_id} | Age: {q.age_minutes:.1f}m",
            f"MC: {_money(q.market_cap_usd)} | Liq: {_money(q.liquidity_usd)}",
            f"5m Vol: {_money(q.volume_5m_usd)} | Buy/Sell: {flow}",
            f"5m: {q.price_change_5m_pct:+.2f}% | 1h: {q.price_change_1h_pct:+.2f}%",
            "Passed: " + ", ".join(q.positives),
        ]
        if failed:
            lines.append("Failed: " + ", ".join(failed))
        if q.warnings:
            lines.append("Warnings: " + ", ".join(q.warnings))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


if __name__ == "__main__":
    print(format_telegram_alerts(find_qualified_tokens()))
