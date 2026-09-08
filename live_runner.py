"""Live Solana observation entry point.

This runner is deliberately read-only. It discovers candidates through
Pump.fun, validates their markets through DexScreener, inspects token state
through Helius, and passes the normalized evidence to the Solana intelligence
engine. It never creates a wallet, signs a transaction, or submits an order.
"""

from __future__ import annotations

import argparse

from solana_observation import run_observation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run read-only Solana live observation")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    print(run_observation(limit=args.limit))


if __name__ == "__main__":
    main()
