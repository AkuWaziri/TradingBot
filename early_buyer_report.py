"""CLI report for read-only holder and early-buyer intelligence."""

from __future__ import annotations

import sys

from early_buyer_intelligence import inspect_early_buyers
from helius_onchain import HeliusProvider


def format_report(result) -> str:
    lines = [
        "👛 SOLANA HOLDER / EARLY-BUYER INTELLIGENCE",
        "────────────────────",
        f"🧾 CA: {result.mint}",
        f"📡 Signatures scanned: {result.signatures_scanned}",
        f"⛓️ Transactions parsed: {result.transactions_parsed}",
        f"👥 Early buyers observed: {result.unique_early_buyers}",
        f"⚠️ Incomplete transactions: {result.incomplete_transactions}",
    ]
    if result.top_buyer_share_of_observed_buys is not None:
        lines.append(f"🎯 Top buyer share of observed spend: {result.top_buyer_share_of_observed_buys:.1%}")
    if not result.early_buyers:
        lines.append("📭 No conservative early-buy observations found")
    else:
        lines.append("")
        lines.append("Early buyers:")
        for index, buyer in enumerate(result.early_buyers[:10], start=1):
            lines.append(
                f"#{index} {buyer.wallet} | first_slot={buyer.first_buy_slot} "
                f"buys={buyer.observed_buys} "
                f"SOL_spent={buyer.native_spent_lamports / 1_000_000_000:.4f}"
            )
    lines.extend([
        "",
        "🛡️ READ-ONLY · MANUAL TRADING ONLY",
        "🔒 Execution: DISABLED",
        "ℹ️ Early-buy labels are conservative observations, not proof of intent or coordination.",
    ])
    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        raise SystemExit("Usage: python early_buyer_report.py <solana_mint>")
    result = inspect_early_buyers(sys.argv[1])
    print(format_report(result))


if __name__ == "__main__":
    main()
