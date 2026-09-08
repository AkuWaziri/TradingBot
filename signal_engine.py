"""Explainable signal scoring for live memecoin observation.

This layer proposes signals. It never executes trades and does not replace risk.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from live_market import LiveToken


@dataclass(frozen=True)
class SignalConfig:
    buy_score: int = 4
    strong_buy_score: int = 6
    max_coingecko_price_divergence_pct: float = 15.0


@dataclass(frozen=True)
class Signal:
    action: str
    score: int
    reasons: tuple[str, ...]


def score_token(
    token: LiveToken,
    *,
    pump_price_usd: float | None = None,
    fomo_activity_score: int = 0,
    config: SignalConfig | None = None,
) -> Signal:
    cfg = config or SignalConfig()
    if cfg.buy_score < 1 or cfg.strong_buy_score < cfg.buy_score:
        raise ValueError("invalid signal thresholds")
    if cfg.max_coingecko_price_divergence_pct < 0:
        raise ValueError("price divergence threshold cannot be negative")

    score = 0
    reasons: list[str] = []

    has_momentum = (
        token.price_change_24h_pct is not None
        and token.price_change_24h_pct >= 10
    )
    has_turnover = False
    if token.volume_24h_usd is not None and token.market_cap_usd:
        turnover = token.volume_24h_usd / token.market_cap_usd
        has_turnover = turnover >= 0.25
        if has_turnover:
            score += 2
            reasons.append("strong volume relative to market cap")

    if has_momentum:
        score += 2
        reasons.append("positive 24h momentum")

    # Liquidity is a risk-quality confirmation, not standalone bullish evidence.
    # Do not let a liquid but directionless token accumulate signal score.
    if token.liquidity_usd is not None and token.liquidity_usd >= 25_000:
        if has_momentum or has_turnover or fomo_activity_score > 0:
            score += 1
            reasons.append("minimum liquidity confirmed")

    if fomo_activity_score > 0:
        score += min(fomo_activity_score, 3)
        reasons.append("FOMO activity confirmation")

    if pump_price_usd and token.price_usd:
        divergence = abs(token.price_usd - pump_price_usd) / pump_price_usd * 100
        if divergence > cfg.max_coingecko_price_divergence_pct:
            return Signal("REJECT", score, tuple(reasons + ["cross-source price divergence too high"]))
        reasons.append("cross-source price check passed")

    if score >= cfg.strong_buy_score:
        return Signal("STRONG_BUY", score, tuple(reasons))
    if score >= cfg.buy_score:
        return Signal("BUY", score, tuple(reasons))
    return Signal("HOLD", score, tuple(reasons or ["insufficient evidence"]))
