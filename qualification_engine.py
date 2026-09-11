"""Read-only Solana token qualification engine.

The engine never trades. It converts normalized market and on-chain evidence
into a deterministic 0-100 qualification score and hard-risk decision.

Eight market/structure checks retain equal weighting from the previous brain:
12.5 points each. Hard safety failures are never compensated by score.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from dexscreener_market import DexScreenerPair
from helius_onchain import SolanaTokenState
from live_market import LiveToken
from solana_intelligence import build_market_features, build_onchain_features, IntelligenceConfig


@dataclass(frozen=True)
class Qualification:
    mint: str
    symbol: str
    name: str
    pair_address: str
    dex_id: str
    score: float
    qualified: bool
    hard_flags: tuple[str, ...]
    positives: tuple[str, ...]
    warnings: tuple[str, ...]
    market_cap_usd: float
    liquidity_usd: float
    price_usd: float
    age_minutes: float
    volume_5m_usd: float
    buy_sell_ratio_5m: float | None
    price_change_5m_pct: float
    price_change_1h_pct: float

    def validate(self) -> None:
        if not self.mint or not self.symbol or not self.pair_address:
            raise ValueError("token identity is required")
        if not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")


class Qualifier:
    """Deterministic qualification using the established rules and weights."""

    WEIGHT = 12.5

    def __init__(self, config: IntelligenceConfig | None = None, minimum_score: float = 75.0) -> None:
        self.config = config or IntelligenceConfig()
        self.minimum_score = minimum_score

    def evaluate(
        self,
        token: LiveToken,
        pair: DexScreenerPair,
        state: SolanaTokenState,
        *,
        now: datetime | None = None,
    ) -> Qualification:
        now = now or datetime.now(timezone.utc)
        hard: list[str] = []
        positives: list[str] = []
        warnings: list[str] = []

        if token.mint != pair.base_token_address or token.mint != state.mint:
            hard.append("mint_identity_mismatch")
        if pair.chain_id != "solana":
            hard.append("non_solana_market")
        if pair.price_usd is None or pair.price_usd <= 0:
            hard.append("invalid_price")
        if pair.liquidity_usd is None or pair.liquidity_usd <= 0:
            hard.append("invalid_liquidity")
        if pair.market_cap_usd is None or pair.market_cap_usd <= 0:
            hard.append("invalid_market_cap")

        try:
            market = build_market_features(pair, now=now)
            onchain = build_onchain_features(state)
        except ValueError as exc:
            hard.append(f"invalid_intelligence:{exc}")
            market = None
            onchain = None

        if onchain is not None:
            if onchain.mint_authority_present:
                hard.append("mint_authority_present")
            if onchain.freeze_authority_present:
                hard.append("freeze_authority_present")
            if not onchain.supply_available:
                hard.append("token_supply_unavailable")
            if onchain.top_account_share is None:
                warnings.append("holder_concentration_unavailable")
            elif onchain.top_account_share > self.config.max_top_account_share:
                hard.append("top_token_account_concentration_too_high")
            if onchain.top_5_account_share is not None and onchain.top_5_account_share > self.config.max_top_5_account_share:
                hard.append("top_5_token_account_concentration_too_high")

        score = 0.0
        if market is not None and onchain is not None and not hard:
            checks = (
                (market.liquidity_usd >= self.config.min_liquidity_usd, "liquidity_pass"),
                (market.liquidity_to_mcap >= self.config.min_liquidity_to_mcap, "liquidity_ratio_pass"),
                (market.volume_5m_usd >= self.config.min_volume_5m_usd, "recent_volume_pass"),
                (market.buy_sell_ratio_5m is not None and market.buy_sell_ratio_5m >= self.config.min_buy_sell_ratio_5m, "buy_pressure_pass"),
                (market.price_change_5m_pct >= self.config.min_momentum_5m_pct, "5m_momentum_pass"),
                (market.price_change_1h_pct >= self.config.min_momentum_1h_pct, "1h_momentum_pass"),
                (market.age_minutes >= self.config.min_age_minutes, "age_confirmation_pass"),
                (not onchain.mint_authority_present and not onchain.freeze_authority_present, "authority_safety_pass"),
            )
            passed = 0
            for condition, label in checks:
                if condition:
                    passed += 1
                    positives.append(label)
            score = passed * self.WEIGHT

            if market.age_minutes > self.config.max_age_minutes:
                hard.append("market_pair_too_old")
            if not self.config.min_market_cap_usd <= market.market_cap_usd <= self.config.max_market_cap_usd:
                hard.append("market_cap_outside_range")
            if market.volume_5m_usd < self.config.min_volume_5m_usd:
                warnings.append("insufficient_recent_volume")
            if market.buy_sell_ratio_5m is None:
                warnings.append("missing_5m_flow_data")
            elif market.buy_sell_ratio_5m < self.config.min_buy_sell_ratio_5m:
                warnings.append("weak_buy_pressure")
            if market.price_change_5m_pct < self.config.min_momentum_5m_pct:
                warnings.append("negative_5m_momentum")
            if market.price_change_1h_pct < self.config.min_momentum_1h_pct:
                warnings.append("negative_1h_momentum")

        qualified = not hard and score >= self.minimum_score
        if not qualified and not hard and score < self.minimum_score:
            warnings.append(f"score_below_threshold:{self.minimum_score:.0f}")

        if market is None:
            raise ValueError("market intelligence unavailable")

        result = Qualification(
            mint=token.mint,
            symbol=pair.base_token_symbol or token.symbol or "UNKNOWN",
            name=pair.base_token_name or token.name or "Unknown",
            pair_address=pair.pair_address,
            dex_id=pair.dex_id,
            score=round(score, 2),
            qualified=qualified,
            hard_flags=tuple(dict.fromkeys(hard)),
            positives=tuple(positives),
            warnings=tuple(dict.fromkeys(warnings)),
            market_cap_usd=market.market_cap_usd,
            liquidity_usd=market.liquidity_usd,
            price_usd=market.price_usd,
            age_minutes=market.age_minutes,
            volume_5m_usd=market.volume_5m_usd,
            buy_sell_ratio_5m=market.buy_sell_ratio_5m,
            price_change_5m_pct=market.price_change_5m_pct,
            price_change_1h_pct=market.price_change_1h_pct,
        )
        result.validate()
        return result
