"""Deterministic Solana token intelligence and decision engine.

This layer combines already-normalized provider observations. It does not call
networks, place orders, sign transactions, or override the risk engine.

Decision states:
    REJECT   - hard safety/data failure.
    NO_TRADE - data is usable, but the setup is not sufficiently strong.
    WATCH    - promising setup that needs more confirmation.
    BUY      - market/on-chain gates pass; risk and execution gates still apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite

from dexscreener_market import DexScreenerPair
from helius_onchain import SolanaTokenState
from live_market import LiveToken


DECISIONS = ("BUY", "WATCH", "NO_TRADE", "REJECT")


@dataclass(frozen=True)
class IntelligenceConfig:
    min_liquidity_usd: float = 25_000.0
    min_market_cap_usd: float = 50_000.0
    max_market_cap_usd: float = 25_000_000.0
    min_age_minutes: float = 2.0
    max_age_minutes: float = 180.0
    min_volume_5m_usd: float = 500.0
    min_buy_sell_ratio_5m: float = 1.10
    min_liquidity_to_mcap: float = 0.02
    max_top_account_share: float = 0.20
    max_top_5_account_share: float = 0.45
    min_momentum_5m_pct: float = 0.0
    min_momentum_1h_pct: float = 0.0
    min_data_freshness_seconds: float = 180.0


@dataclass(frozen=True)
class MarketFeatures:
    price_usd: float
    liquidity_usd: float
    market_cap_usd: float
    fdv_usd: float | None
    age_minutes: float
    volume_5m_usd: float
    volume_1h_usd: float
    buy_sell_ratio_5m: float | None
    buy_sell_ratio_1h: float | None
    price_change_5m_pct: float
    price_change_1h_pct: float
    price_change_6h_pct: float | None
    liquidity_to_mcap: float
    volume_5m_to_mcap: float


@dataclass(frozen=True)
class OnchainFeatures:
    mint_authority_present: bool
    freeze_authority_present: bool
    top_account_share: float | None
    top_5_account_share: float | None
    top_20_account_share: float | None
    token_program: str | None
    supply_available: bool


@dataclass(frozen=True)
class SolanaIntelligence:
    mint: str
    symbol: str
    pair_address: str
    dex_id: str
    market: MarketFeatures | None
    onchain: OnchainFeatures | None
    hard_risk_flags: tuple[str, ...]
    warnings: tuple[str, ...]
    decision: str
    confidence: float
    reasons: tuple[str, ...]

    def validate(self) -> None:
        if self.decision not in DECISIONS:
            raise ValueError("invalid decision")
        if not self.mint or not self.symbol or not self.pair_address:
            raise ValueError("token identifiers are required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    value = numerator / denominator
    return value if isfinite(value) else None


def _tx_ratio(buys: int | None, sells: int | None) -> float | None:
    if buys is None or sells is None:
        return None
    if sells == 0:
        return float("inf") if buys > 0 else 1.0
    return buys / sells


def _account_share(raw_amount: int, supply_raw: int | None) -> float | None:
    if supply_raw is None or supply_raw <= 0:
        return None
    share = raw_amount / supply_raw
    return share if isfinite(share) and 0 <= share <= 1 else None


def _age_minutes(created_at: datetime | None, now: datetime) -> float | None:
    if created_at is None:
        return None
    if created_at.tzinfo is None:
        return None
    age = (now - created_at.astimezone(timezone.utc)).total_seconds() / 60.0
    return age if isfinite(age) else None


def build_market_features(pair: DexScreenerPair, *, now: datetime | None = None) -> MarketFeatures:
    now = now or datetime.now(timezone.utc)
    if pair.price_usd is None or pair.liquidity_usd is None or pair.market_cap_usd is None:
        raise ValueError("price, liquidity and market cap are required")
    age = _age_minutes(pair.pair_created_at, now)
    if age is None:
        raise ValueError("pair creation time is required")
    if age < 0:
        raise ValueError("pair creation time is in the future")
    return MarketFeatures(
        price_usd=pair.price_usd,
        liquidity_usd=pair.liquidity_usd,
        market_cap_usd=pair.market_cap_usd,
        fdv_usd=pair.fdv_usd,
        age_minutes=age,
        volume_5m_usd=pair.volume_5m_usd or 0.0,
        volume_1h_usd=pair.volume_1h_usd or 0.0,
        buy_sell_ratio_5m=_tx_ratio(pair.buys_5m, pair.sells_5m),
        buy_sell_ratio_1h=_tx_ratio(pair.buys_1h, pair.sells_1h),
        price_change_5m_pct=pair.price_change_5m_pct or 0.0,
        price_change_1h_pct=pair.price_change_1h_pct or 0.0,
        price_change_6h_pct=pair.price_change_6h_pct,
        liquidity_to_mcap=_safe_ratio(pair.liquidity_usd, pair.market_cap_usd) or 0.0,
        volume_5m_to_mcap=_safe_ratio(pair.volume_5m_usd, pair.market_cap_usd) or 0.0,
    )


def build_onchain_features(state: SolanaTokenState) -> OnchainFeatures:
    supply = state.supply_raw
    shares = [_account_share(account.raw_amount, supply) for account in state.top_accounts]
    valid = [share for share in shares if share is not None]
    return OnchainFeatures(
        mint_authority_present=bool(state.mint_authority),
        freeze_authority_present=bool(state.freeze_authority),
        top_account_share=valid[0] if valid else None,
        top_5_account_share=sum(valid[:5]) if valid else None,
        top_20_account_share=sum(valid[:20]) if valid else None,
        token_program=state.token_program,
        supply_available=supply is not None and supply > 0,
    )


def _select_reason(reasons: list[str], text: str) -> None:
    if text not in reasons:
        reasons.append(text)


def evaluate_token(
    token: LiveToken,
    pair: DexScreenerPair,
    state: SolanaTokenState,
    *,
    config: IntelligenceConfig | None = None,
    now: datetime | None = None,
) -> SolanaIntelligence:
    """Build a deterministic decision from three normalized observations."""
    config = config or IntelligenceConfig()
    now = now or datetime.now(timezone.utc)
    market: MarketFeatures | None = None
    onchain: OnchainFeatures | None = None
    hard: list[str] = []
    warnings: list[str] = []
    reasons: list[str] = []

    if token.mint != pair.base_token_address or token.mint != state.mint:
        hard.append("mint_identity_mismatch")
    if pair.chain_id != "solana":
        hard.append("non_solana_market")
    if pair.price_usd is None or pair.price_usd <= 0:
        hard.append("missing_or_invalid_price")
    if pair.liquidity_usd is None or pair.liquidity_usd <= 0:
        hard.append("missing_or_invalid_liquidity")
    if pair.market_cap_usd is None or pair.market_cap_usd <= 0:
        hard.append("missing_or_invalid_market_cap")

    try:
        market = build_market_features(pair, now=now)
    except ValueError as exc:
        hard.append(f"market_data_invalid:{exc}")

    try:
        onchain = build_onchain_features(state)
    except (ValueError, ZeroDivisionError) as exc:
        hard.append(f"onchain_data_invalid:{exc}")

    if onchain is not None:
        if onchain.mint_authority_present:
            hard.append("mint_authority_present")
        if onchain.freeze_authority_present:
            hard.append("freeze_authority_present")
        if onchain.top_account_share is None:
            warnings.append("holder_concentration_unavailable")
        elif onchain.top_account_share > config.max_top_account_share:
            hard.append("top_token_account_concentration_too_high")
        if onchain.top_5_account_share is not None and onchain.top_5_account_share > config.max_top_5_account_share:
            hard.append("top_5_token_account_concentration_too_high")
        if not onchain.supply_available:
            hard.append("token_supply_unavailable")

    if market is not None:
        if market.age_minutes < config.min_age_minutes:
            warnings.append("too_new_for_confirmation")
        if market.age_minutes > config.max_age_minutes:
            hard.append("market_pair_too_old")
        if market.liquidity_usd < config.min_liquidity_usd:
            hard.append("liquidity_below_minimum")
        if not config.min_market_cap_usd <= market.market_cap_usd <= config.max_market_cap_usd:
            hard.append("market_cap_outside_range")
        if market.liquidity_to_mcap < config.min_liquidity_to_mcap:
            warnings.append("weak_liquidity_to_market_cap")
        if market.volume_5m_usd < config.min_volume_5m_usd:
            warnings.append("insufficient_recent_volume")
        if market.buy_sell_ratio_5m is None:
            warnings.append("missing_5m_flow_data")
        elif market.buy_sell_ratio_5m < config.min_buy_sell_ratio_5m:
            warnings.append("weak_buy_pressure")
        if market.price_change_5m_pct < config.min_momentum_5m_pct:
            warnings.append("negative_5m_momentum")
        if market.price_change_1h_pct < config.min_momentum_1h_pct:
            warnings.append("negative_1h_momentum")

    if hard:
        decision = "REJECT"
        confidence = 0.0
        reasons.extend(hard[:4])
    elif market is None or onchain is None:
        decision = "NO_TRADE"
        confidence = 0.0
        reasons.append("incomplete_intelligence")
    else:
        positive = 0
        checks = 0
        for condition, text in (
            (market.liquidity_usd >= config.min_liquidity_usd, "liquidity_pass"),
            (market.liquidity_to_mcap >= config.min_liquidity_to_mcap, "liquidity_ratio_pass"),
            (market.volume_5m_usd >= config.min_volume_5m_usd, "recent_volume_pass"),
            (market.buy_sell_ratio_5m is not None and market.buy_sell_ratio_5m >= config.min_buy_sell_ratio_5m, "buy_pressure_pass"),
            (market.price_change_5m_pct >= config.min_momentum_5m_pct, "5m_momentum_pass"),
            (market.price_change_1h_pct >= config.min_momentum_1h_pct, "1h_momentum_pass"),
            (market.age_minutes >= config.min_age_minutes, "age_confirmation_pass"),
            (not onchain.mint_authority_present and not onchain.freeze_authority_present, "authority_safety_pass"),
        ):
            checks += 1
            if condition:
                positive += 1
                _select_reason(reasons, text)

        confidence = positive / checks if checks else 0.0
        if positive == checks and market.age_minutes >= config.min_age_minutes:
            decision = "BUY"
        elif positive >= 5:
            decision = "WATCH"
        else:
            decision = "NO_TRADE"

        for warning in warnings[:3]:
            _select_reason(reasons, warning)

    result = SolanaIntelligence(
        mint=token.mint,
        symbol=pair.base_token_symbol or token.symbol,
        pair_address=pair.pair_address,
        dex_id=pair.dex_id,
        market=market,
        onchain=onchain,
        hard_risk_flags=tuple(dict.fromkeys(hard)),
        warnings=tuple(dict.fromkeys(warnings)),
        decision=decision,
        confidence=round(confidence, 4),
        reasons=tuple(reasons),
    )
    result.validate()
    return result
