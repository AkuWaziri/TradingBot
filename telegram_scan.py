"""Telegram delivery for read-only Solana scan and mature qualification results.

This module has no trading, wallet, signing, or transaction functionality.
"""

from __future__ import annotations

import os
import urllib.error
import urllib.parse
import urllib.request

from qualified_monitor import format_telegram_alerts, scan_tokens, summarize_rejections
from telegram_advanced import TelegramAdvancedReport, format_advanced_section


TELEGRAM_MAX_TEXT = 4096
TELEGRAM_SAFE_TEXT = 3900


def _send_one_telegram(text: str) -> None:
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


def _telegram_chunks(text: str, limit: int = TELEGRAM_SAFE_TEXT) -> list[str]:
    """Split at section boundaries so long research reports remain readable."""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""
    for section in text.split("\n\n"):
        candidate = section if not current else current + "\n\n" + section
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(section) <= limit:
            current = section
            continue
        for start in range(0, len(section), limit):
            chunks.append(section[start:start + limit])
        current = ""
    if current:
        chunks.append(current)
    return chunks


def send_telegram(text: str) -> None:
    """Send one or more Telegram messages without exceeding Telegram's text limit."""
    for chunk in _telegram_chunks(text):
        if len(chunk) > TELEGRAM_MAX_TEXT:
            raise RuntimeError("Telegram message chunk exceeds the platform limit")
        _send_one_telegram(chunk)


def _append_rejection_group(lines: list[str], title: str, entries: tuple[tuple[str, int], ...]) -> None:
    if not entries:
        return
    lines.append(title)
    for reason, count in entries:
        lines.append(f"• {reason}: {count}")


def format_scan_status(scan) -> str:
    lines = [
        "🔎 SOLANA MONITOR",
        "────────────────────",
        "📡 Scan completed",
        "🧠 Mature qualification: core gates + advanced risk gates",
        f"🎯 Candidates discovered: {scan.discovered}/{scan.requested}",
        f"📊 Market data available: {scan.market_data_available}",
        f"⛓️ Core evaluated: {scan.evaluated}",
        f"🧪 Core-qualified: {scan.core_qualified}",
        f"🔬 Advanced evaluated: {scan.advanced_evaluated}",
        f"🟢 Mature qualified: {len(scan.qualified)}",
        "",
    ]

    grouped = summarize_rejections(scan.rejection_reasons)
    _append_rejection_group(lines, "🔴 Risk rejected:", grouped["risk_rejection"])
    _append_rejection_group(lines, "⚫ Data insufficient:", grouped["data_insufficient"])
    _append_rejection_group(lines, "🟠 Provider / technical failure:", grouped["provider_failure"])
    if not any(grouped.values()):
        lines.append("📭 No rejection data recorded")

    lines.extend([
        "",
        "🛡️ READ-ONLY · MANUAL TRADING ONLY",
        "🔒 Execution: DISABLED",
    ])
    return "\n".join(lines)


def build_message(scan) -> str:
    sections = [format_scan_status(scan)]
    if not scan.qualified:
        sections.append(format_telegram_alerts([]))
        return "\n\n".join(sections)

    sections.append(format_telegram_alerts(list(scan.qualified)))
    reports_by_mint = {mint: (intelligence, advanced) for mint, intelligence, advanced in scan.advanced_reports}
    for qualification in sorted(scan.qualified, key=lambda item: item.score, reverse=True):
        item = reports_by_mint.get(qualification.mint)
        if item is None:
            continue
        intelligence, advanced = item
        report = TelegramAdvancedReport(intelligence)
        advanced_lines = [
            f"🧠 Advanced risk: {advanced.risk_level}",
            f"📚 Evidence window: {advanced.evidence_coverage:.0%}",
        ]
        if advanced.warnings:
            advanced_lines.append("⚠️ Advanced warnings: " + ", ".join(advanced.warnings))
        sections.append(
            f"🧾 {qualification.symbol} · {qualification.mint}\n"
            + format_advanced_section(report)
            + "\n"
            + "\n".join(advanced_lines)
        )
    return "\n\n".join(sections)


def main() -> None:
    limit = int(os.getenv("OBSERVATION_LIMIT", "30"))
    scan = scan_tokens(limit=limit)
    message = build_message(scan)

    send_telegram(message)
    print(
        "Telegram scan report sent; "
        f"discovered={scan.discovered}; "
        f"core_evaluated={scan.evaluated}; "
        f"core_qualified={scan.core_qualified}; "
        f"advanced_evaluated={scan.advanced_evaluated}; "
        f"qualified={len(scan.qualified)}; "
        f"advanced_reports={len(scan.advanced_reports)}; "
        "execution=disabled"
    )


if __name__ == "__main__":
    main()
