"""Read-only Telegram notifier for the Solana observation pipeline.

This module sends observation snapshots only. It cannot sign, build, or submit
transactions and does not contain wallet functionality.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request

from solana_observation import run_observation


class TelegramMonitorError(RuntimeError):
    """Raised when a Telegram notification cannot be delivered."""


def _telegram_send(token: str, chat_id: str, text: str) -> None:
    if not token or not chat_id:
        raise TelegramMonitorError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}
    ).encode("utf-8")
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
        raise TelegramMonitorError(f"Telegram delivery failed: {exc}") from exc

    if '"ok":true' not in body.lower().replace(" ", ""):
        raise TelegramMonitorError("Telegram API rejected the message")


def build_message(limit: int = 10) -> str:
    """Run the read-only Solana observer and return its report."""
    return run_observation(limit=limit)


def main() -> None:
    limit = int(os.getenv("OBSERVATION_LIMIT", "10"))
    if not 1 <= limit <= 30:
        raise ValueError("OBSERVATION_LIMIT must be between 1 and 30")

    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    report = build_message(limit=limit)
    _telegram_send(token, chat_id, report)
    print("Telegram monitoring snapshot sent; execution remains disabled.")


if __name__ == "__main__":
    main()
