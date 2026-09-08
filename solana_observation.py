"""Read-only Solana observation pipeline.

Pipeline: Pump.fun discovery -> DexScreener market validation -> Helius
on-chain inspection -> deterministic Solana intelligence.

This module has no wallet, signer, transaction builder, or execution path.
"""

from __future__ import annotations

from dataclasses import dataclass

from dexscreener_market import DexScreenerPair, DexScreenerProvider
from helius_onchain import HeliusProvider, HeliusOnchainError
from live_market import LiveMarketError, LiveToken, PumpFunProvider
from solana_intelligence import IntelligenceConfig, SolanaIntelligence, evaluate_token


@dataclass(frozen=True)
class Observation:
    token: LiveToken
    pair: DexScreenerPair | None
    intelligence: SolanaIntelligence | None
    error: str | None = None


def _pair_rank(pair: DexScreenerPair) -> tuple[float, float, float, int]:
    """Rank pairs by liquidity first, then recent activity and flow."""
    liquidity = pair.liquidity_usd or 0.0
    volume = pair.volume_5m_usd or 0.0
    buys = pair.buys_5m or 0
    sells = pair.sells_5m or 0
    return liquidity, volume, buys - sells, buys + sells


def select_best_pair(pairs: list[DexScreenerPair], mint: str) -> DexScreenerPair | None:
    candidates = [
        pair for pair in pairs
        if pair.base_token_address == mint and pair.chain_id == "solana"
    ]
    return max(candidates, key=_pair_rank, default=None)


def observe_tokens(
    *,
    limit: int = 10,
    pump: PumpFunProvider | None = None,
    dex: DexScreenerProvider | None = None,
    helius: HeliusProvider | None = None,
    config: IntelligenceConfig | None = None,
) -> list[Observation]:
    if not 1 <= limit <= 30:
        raise ValueError("limit must be between 1 and 30")

    pump = pump or PumpFunProvider()
    dex = dex or DexScreenerProvider()
    helius = helius or HeliusProvider()

    tokens = pump.currently_live(limit=limit)
    if not tokens:
        return []

    pairs = dex.pairs_by_tokens([token.mint for token in tokens])
    grouped: dict[str, list[DexScreenerPair]] = {}
    for pair in pairs:
        grouped.setdefault(pair.base_token_address, []).append(pair)

    observations: list[Observation] = []
    for token in tokens:
        pair = select_best_pair(grouped.get(token.mint, []), token.mint)
        if pair is None:
            observations.append(Observation(token=token, pair=None, intelligence=None, error="no_solana_market_pair"))
            continue

        try:
            state = helius.inspect_token(token.mint)
            intelligence = evaluate_token(token, pair, state, config=config)
        except (HeliusOnchainError, ValueError) as exc:
            observations.append(
                Observation(token=token, pair=pair, intelligence=None, error=f"helius_or_brain_failure:{exc}")
            )
            continue

        observations.append(Observation(token=token, pair=pair, intelligence=intelligence))

    return observations


def format_observations(observations: list[Observation]) -> str:
    lines = [
        "SOLANA LIVE OBSERVATION",
        "mode=read-only; execution=disabled",
        f"candidates={len(observations)}",
        "",
    ]

    for observation in observations:
        token = observation.token
        identity = token.symbol or token.mint[:8]
        if observation.pair is None:
            lines.append(f"NO_TRADE {identity} | mint={token.mint} | reason={observation.error}")
            continue

        pair = observation.pair
        intelligence = observation.intelligence
        if intelligence is None:
            lines.append(
                f"NO_TRADE {identity} | dex={pair.dex_id} | liq=${pair.liquidity_usd or 0:.4g} "
                f"mcap=${pair.market_cap_usd or 0:.4g} | reason={observation.error}"
            )
            continue

        market = intelligence.market
        onchain = intelligence.onchain
        lines.append(
            f"{intelligence.decision} {identity} | confidence={intelligence.confidence:.2f} "
            f"dex={intelligence.dex_id} "
            f"age={market.age_minutes:.1f}m "
            f"liq=${market.liquidity_usd:.4g} "
            f"mcap=${market.market_cap_usd:.4g} "
            f"vol5m=${market.volume_5m_usd:.4g} "
            f"flow5m={market.buy_sell_ratio_5m if market.buy_sell_ratio_5m is not None else 'N/A'} "
            f"m5={market.price_change_5m_pct:.3g}% "
            f"h1={market.price_change_1h_pct:.3g}% "
            f"top_account={onchain.top_account_share:.2% if onchain.top_account_share is not None else 'N/A'} "
            f"reasons={';'.join(intelligence.reasons[:4])}"
        )

    return "\n".join(lines)


def run_observation(*, limit: int = 10) -> str:
    try:
        observations = observe_tokens(limit=limit)
    except (LiveMarketError, HeliusOnchainError) as exc:
        return "\n".join([
            "SOLANA LIVE OBSERVATION",
            "mode=read-only; execution=disabled",
            f"FAIL_CLOSED: {exc}",
            "NO SIGNALS GENERATED",
        ])
    return format_observations(observations)


if __name__ == "__main__":
    print(run_observation())
