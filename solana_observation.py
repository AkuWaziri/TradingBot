"""Read-only Solana observation pipeline.

Pipeline: DexScreener discovery -> market validation -> Helius on-chain
inspection -> deterministic Solana intelligence.

DexScreener is used only as an interim scheduled discovery source. Production
real-time discovery will move to direct Solana event streaming. This module has
no wallet, signer, transaction builder, or execution path.
"""

from __future__ import annotations

from dataclasses import dataclass

from dexscreener_market import DexScreenerPair, DexScreenerProvider
from helius_onchain import HeliusProvider, HeliusOnchainError
from live_market import LiveMarketError, LiveToken
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


def _token_from_pair(pair: DexScreenerPair) -> LiveToken:
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


def observe_tokens(
    *,
    limit: int = 10,
    dex: DexScreenerProvider | None = None,
    helius: HeliusProvider | None = None,
    config: IntelligenceConfig | None = None,
) -> list[Observation]:
    if not 1 <= limit <= 30:
        raise ValueError("limit must be between 1 and 30")

    dex = dex or DexScreenerProvider()
    helius = helius or HeliusProvider()

    mints = dex.latest_solana_token_addresses(limit=limit)
    if not mints:
        return []

    pairs = dex.pairs_by_tokens(mints)
    grouped: dict[str, list[DexScreenerPair]] = {}
    for pair in pairs:
        grouped.setdefault(pair.base_token_address, []).append(pair)

    observations: list[Observation] = []
    for mint in mints:
        pair = select_best_pair(grouped.get(mint, []), mint)
        if pair is None:
            token = LiveToken(
                mint=mint,
                symbol="UNKNOWN",
                name="Unknown",
                price_usd=None,
                market_cap_usd=None,
                volume_24h_usd=None,
                price_change_24h_pct=None,
                liquidity_usd=None,
                created_at=None,
                source="dexscreener-discovery",
            )
            observations.append(Observation(token=token, pair=None, intelligence=None, error="no_solana_market_pair"))
            continue

        try:
            token = _token_from_pair(pair)
            state = helius.inspect_token(mint)
            intelligence = evaluate_token(token, pair, state, config=config)
        except (HeliusOnchainError, LiveMarketError, ValueError) as exc:
            try:
                token = _token_from_pair(pair)
            except ValueError:
                token = LiveToken(
                    mint=mint,
                    symbol=pair.base_token_symbol or "UNKNOWN",
                    name=pair.base_token_name or "Unknown",
                    price_usd=pair.price_usd,
                    market_cap_usd=pair.market_cap_usd,
                    volume_24h_usd=pair.volume_24h_usd,
                    price_change_24h_pct=pair.price_change_24h_pct,
                    liquidity_usd=pair.liquidity_usd,
                    created_at=pair.pair_created_at,
                    source="dexscreener",
                )
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
        "discovery=dexscreener-scheduled; realtime-discovery=planned",
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
        top_account = (
            f"{onchain.top_account_share:.2%}"
            if onchain.top_account_share is not None
            else "N/A"
        )
        flow = (
            f"{market.buy_sell_ratio_5m:.2f}"
            if market.buy_sell_ratio_5m is not None and market.buy_sell_ratio_5m != float("inf")
            else ("inf" if market.buy_sell_ratio_5m is not None else "N/A")
        )
        lines.append(
            f"{intelligence.decision} {identity} | confidence={intelligence.confidence:.2f} "
            f"dex={intelligence.dex_id} "
            f"age={market.age_minutes:.1f}m "
            f"liq=${market.liquidity_usd:.4g} "
            f"mcap=${market.market_cap_usd:.4g} "
            f"vol5m=${market.volume_5m_usd:.4g} "
            f"flow5m={flow} "
            f"m5={market.price_change_5m_pct:.3g}% "
            f"h1={market.price_change_1h_pct:.3g}% "
            f"top_account={top_account} "
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
