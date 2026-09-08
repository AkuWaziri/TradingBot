"""Deterministic safety filters for live token observation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from live_market import LiveToken


@dataclass(frozen=True)
class FilterConfig:
    min_market_cap_usd: float = 25_000.0
    max_market_cap_usd: float = 25_000_000.0
    min_volume_24h_usd: float = 10_000.0
    max_age_minutes: int = 180

    def validate(self) -> None:
        if self.min_market_cap_usd < 0 or self.max_market_cap_usd <= 0:
            raise ValueError("market-cap bounds must be non-negative")
        if self.min_market_cap_usd > self.max_market_cap_usd:
            raise ValueError("minimum market cap cannot exceed maximum")
        if self.min_volume_24h_usd < 0:
            raise ValueError("minimum volume cannot be negative")
        if self.max_age_minutes <= 0:
            raise ValueError("max_age_minutes must be positive")


@dataclass(frozen=True)
class FilterDecision:
    accepted: bool
    reasons: tuple[str, ...]


def evaluate_token(
    token: LiveToken,
    config: FilterConfig,
    *,
    now: datetime | None = None,
) -> FilterDecision:
    config.validate()
    reasons: list[str] = []
    if token.price_usd is None or token.price_usd <= 0:
        reasons.append("missing valid price")
    if token.market_cap_usd is None:
        reasons.append("missing market cap")
    elif not config.min_market_cap_usd <= token.market_cap_usd <= config.max_market_cap_usd:
        reasons.append("market cap outside configured range")
    if token.volume_24h_usd is None or token.volume_24h_usd < config.min_volume_24h_usd:
        reasons.append("insufficient 24h volume")
    if token.created_at is not None:
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        age_minutes = (current - token.created_at).total_seconds() / 60
        if age_minutes < 0:
            reasons.append("future token timestamp")
        elif age_minutes > config.max_age_minutes:
            reasons.append("token too old for early-entry strategy")
    return FilterDecision(not reasons, tuple(reasons))
