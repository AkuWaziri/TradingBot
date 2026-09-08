"""Live observation runner.

The runner is deliberately read-only: it discovers tokens, cross-checks data,
filters them, scores them, and prints what the bot *would* consider. It never
creates a wallet, signs a transaction, or submits an order.
"""

from __future__ import annotations

import argparse

from live_market import CoinGeckoProvider, LiveMarketError, PumpFunProvider
from signal_engine import score_token
from token_filter import FilterConfig, evaluate_token


def run_observation(*, limit: int = 20) -> str:
    pump = PumpFunProvider()
    tokens = pump.currently_live(limit=limit)
    if not tokens:
        return "LIVE OBSERVATION\nNo valid Pump.fun tokens returned."

    try:
        tokens = CoinGeckoProvider().enrich(tokens)
        coingecko_status = "connected"
    except LiveMarketError as exc:
        # Fail closed for scoring that depends on the cross-check. Discovery is
        # still reported so provider failures are visible rather than hidden.
        coingecko_status = f"unavailable: {exc}"

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
        if not decision.accepted:
            lines.append(f"REJECT {token.symbol or token.mint}: {'; '.join(decision.reasons)}")
            continue
        signal = score_token(token)
        lines.append(
            f"{signal.action} {token.symbol or token.mint} score={signal.score} "
            f"price=${token.price_usd} mcap=${token.market_cap_usd} "
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
