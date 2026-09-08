"""Live observation runner.

The runner is deliberately read-only: it discovers tokens, cross-checks data,
filters them, scores them, and prints what the bot *would* consider. It never
creates a wallet, signs a transaction, or submits an order.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from live_market import CoinGeckoProvider, LiveMarketError, PumpFunProvider, LiveToken
from signal_engine import score_token
from token_filter import FilterConfig, evaluate_token


def _age_minutes(token: LiveToken) -> float | None:
    if token.created_at is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - token.created_at).total_seconds() / 60)


def _fmt(value: float | None, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    return f"{value:.4g}{suffix}"


def run_observation(*, limit: int = 20) -> str:
    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")

    pump = PumpFunProvider()
    tokens = pump.currently_live(limit=limit)
    if not tokens:
        return "LIVE OBSERVATION\nNo valid Pump.fun tokens returned."

    try:
        tokens = CoinGeckoProvider().enrich(tokens)
        coingecko_status = "connected"
    except LiveMarketError as exc:
        # CoinGecko supplies the USD price used by the current signal/filter
        # pipeline. Do not score anything when this required cross-check fails.
        return "\n".join(
            [
                "LIVE OBSERVATION",
                "mode=read-only; execution=disabled",
                f"pump.fun tokens={len(tokens)}",
                f"coingecko=FAIL_CLOSED: {exc}",
                "",
                "NO SIGNALS GENERATED",
                "Reason: required CoinGecko cross-check is unavailable.",
            ]
        )

    filters = FilterConfig()
    lines = [
        "LIVE OBSERVATION",
        "mode=read-only; execution=disabled",
        f"pump.fun tokens={len(tokens)}",
        f"coingecko={coingecko_status}",
        "",
    ]

    for token in tokens:
        decision = evaluate_token(token, filters)
        age = _age_minutes(token)
        identity = token.symbol or token.mint
        stats = (
            f"price=${_fmt(token.price_usd)} "
            f"mcap=${_fmt(token.market_cap_usd)} "
            f"vol24h=${_fmt(token.volume_24h_usd)} "
            f"liq=${_fmt(token.liquidity_usd)} "
            f"chg24h={_fmt(token.price_change_24h_pct, '%')} "
            f"age={_fmt(age, 'm')} "
            f"source={token.source}"
        )
        if not decision.accepted:
            lines.append(
                f"REJECT {identity} | {stats} | "
                f"reasons={'; '.join(decision.reasons)}"
            )
            continue

        signal = score_token(token)
        lines.append(
            f"{signal.action} {identity} score={signal.score} | {stats} | "
            f"reasons={'; '.join(signal.reasons)}"
        )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run read-only live market observation")
    parser.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    print(run_observation(limit=args.limit))


if __name__ == "__main__":
    main()
