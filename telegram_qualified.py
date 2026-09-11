"""Telegram delivery for read-only qualified Solana research alerts.

This module has no trading, wallet, signing, or transaction functionality.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request

from qualified_monitor import ScanResult, scan_tokens, format_telegram_alerts
from telegram_advanced import enrich_qualified, format_advanced_section


def send_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Telegram delivery failed: {exc}") from exc
    if '"ok":true' not in body.lower().replace(" ", ""):
        raise RuntimeError("Telegram API rejected the message")


def _scan_header(scan: ScanResult) -> str:
    lines = [
        "🔎 SOLANA MONITOR",
        "────────────────────",
        f"📡 Candidates discovered: {scan.discovered}/{scan.requested}",
        f"📊 Market data available: {scan.market_data_available}",
        f"⛓️ Evaluated on-chain: {scan.evaluated}",
        f"🟢 Qualified: {len(scan.qualified)}",
    ]
    if scan.rejection_reasons:
        lines.append("🔴 Top rejections:")
        for reason, count in scan.rejection_reasons:
            lines.append(f"• {reason}: {count}")
    lines.extend([
        "🛡️ READ-ONLY · MANUAL TRADING ONLY",
        "🔒 Execution: DISABLED",
    ])
    return "\n".join(lines)


def _build_message(scan: ScanResult) -> str:
    sections = [_scan_header(scan)]
    if not scan.qualified:
        sections.append(format_telegram_alerts([]))
        return "\n\n".join(sections)

    sections.append(format_telegram_alerts(list(scan.qualified)))
    advanced_limit = int(os.getenv("ADVANCED_INTELLIGENCE_LIMIT", "5"))
    signature_limit = int(os.getenv("ADVANCED_SIGNATURE_LIMIT", "50"))
    max_transactions = int(os.getenv("ADVANCED_MAX_TRANSACTIONS", "40"))
    try:
        reports = enrich_qualified(
            list(scan.qualified),
            limit=advanced_limit,
            signature_limit=signature_limit,
            max_transactions=max_transactions,
        )
        for qualification in sorted(scan.qualified, key=lambda item: item.score, reverse=True):
            report = reports.get(qualification.mint)
            if report is not None:
                sections.append(
                    f"\n🧾 {qualification.symbol} · {qualification.mint}\n"
                    + format_advanced_section(report)
                )
    except Exception as exc:
        sections.append(
            "⚠️ Advanced research unavailable for this scan; qualification results are unchanged."
        )
        print(f"Advanced intelligence unavailable: {type(exc).__name__}: {exc}")
    return "\n\n".join(sections)


def main() -> None:
    limit = int(os.getenv("OBSERVATION_LIMIT", "30"))
    scan = scan_tokens(limit=limit)
    message = _build_message(scan)
    send_telegram(message)
    print(
        "Telegram Solana research report sent; "
        f"discovered={scan.discovered}; qualified={len(scan.qualified)}; execution=disabled"
    )


if __name__ == "__main__":
    main()
