"""Telegram delivery for read-only Solana scan results.

This module has no trading, wallet, signing, or transaction functionality.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request

from qualified_monitor import format_telegram_alerts, scan_tokens


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


def format_scan_status(scan) -> str:
    lines = [
        "🔎 SOLANA MONITOR",
        "────────────────────",
        "📡 Scan completed",
        f"🎯 Candidates discovered: {scan.discovered}/{scan.requested}",
        f"📊 Market data available: {scan.market_data_available}",
        f"⛓️ Fully evaluated: {scan.evaluated}",
        f"🟢 Qualified: {len(scan.qualified)}",
        "",
    ]
    if scan.rejection_reasons:
        lines.append("🔴 Main rejection reasons:")
        for reason, count in scan.rejection_reasons:
            lines.append(f"• {reason}: {count}")
    else:
        lines.append("📭 No rejection data recorded")
    lines.extend([
        "",
        "🛡️ READ-ONLY · MANUAL TRADING ONLY",
        "🔒 Execution: DISABLED",
    ])
    return "\n".join(lines)


def main() -> None:
    limit = int(os.getenv("OBSERVATION_LIMIT", "30"))
    scan = scan_tokens(limit=limit)

    if scan.qualified:
        message = format_telegram_alerts(list(scan.qualified))
    else:
        message = format_scan_status(scan)

    send_telegram(message)
    print(
        "Telegram scan report sent; "
        f"discovered={scan.discovered}; "
        f"evaluated={scan.evaluated}; "
        f"qualified={len(scan.qualified)}; "
        "execution=disabled"
    )


if __name__ == "__main__":
    main()
