"""Telegram delivery for qualified Solana token alerts only.

This module has no trading, wallet, signing, or transaction functionality.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request

from qualified_monitor import find_qualified_tokens, format_telegram_alerts


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


def main() -> None:
    limit = int(os.getenv("OBSERVATION_LIMIT", "30"))
    qualified = find_qualified_tokens(limit=limit)
    message = format_telegram_alerts(qualified)
    send_telegram(message)
    print(f"Telegram qualified-token alert sent; qualified={len(qualified)}; execution=disabled")


if __name__ == "__main__":
    main()
