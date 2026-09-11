"""Clean Telegram reporting for the read-only Solana qualification monitor."""

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
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"}).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"Telegram delivery failed: {exc}") from exc
    if '"ok":true' not in body.lower().replace(" ", ""):
        raise RuntimeError("Telegram API rejected the message")


def _telegram_chunks(text: str, limit: int = TELEGRAM_SAFE_TEXT) -> list[str]:
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
    _append_rejection_group(lines, "🟠 Provider / technical:", grouped["provider_failure"])
    lines.extend(["", "🛡️ READ-ONLY · MANUAL TRADING ONLY", "🔒 Execution: DISABLED"])
    return "\n".join(lines)


def _money(value: float) -> str:
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.0f}"


def _core_section(scan) -> str:
    if not scan.core_qualified_tokens:
        return "🟡 CORE-QUALIFIED\n────────────────────\n📭 None in this scan"
    blocks = [
        "🟡 CORE-QUALIFIED",
        "────────────────────",
        f"🔎 {len(scan.core_qualified_tokens)} token{'s' if len(scan.core_qualified_tokens) != 1 else ''} passed the core gates",
        "ℹ️ Research pool · not a trade signal",
    ]
    for index, item in enumerate(sorted(scan.core_qualified_tokens, key=lambda x: x.qualification.score, reverse=True), start=1):
        q = item.qualification
        flow = "N/A" if q.buy_sell_ratio_5m is None else ("∞" if q.buy_sell_ratio_5m == float("inf") else f"{q.buy_sell_ratio_5m:.2f}")
        warning_line = ["⚠️ Core warnings: " + ", ".join(q.warnings)] if q.warnings else []
        blocks.append("\n".join([
            f"\n#{index}  {q.symbol} · {q.score:.0f}/100",
            f"🧾 CA: {q.mint}",
            f"🏦 {q.dex_id} · {q.age_minutes:.1f}m · MC {_money(q.market_cap_usd)} · Liq {_money(q.liquidity_usd)}",
            f"📈 5m {q.price_change_5m_pct:+.2f}% · 1h {q.price_change_1h_pct:+.2f}% · Vol {_money(q.volume_5m_usd)} · B/S {flow}",
            f"🧪 Mature status: {item.mature_status}",
            "✅ Core: " + ", ".join(q.positives),
            *warning_line,
        ]))
    return "\n\n".join(blocks)


def build_message(scan) -> str:
    sections = [format_scan_status(scan), _core_section(scan), format_telegram_alerts(list(scan.qualified))]
    reports_by_mint = {mint: (intelligence, advanced) for mint, intelligence, advanced in scan.advanced_reports}
    for qualification in sorted(scan.qualified, key=lambda item: item.score, reverse=True):
        item = reports_by_mint.get(qualification.mint)
        if item is None:
            continue
        intelligence, advanced = item
        report = TelegramAdvancedReport(intelligence)
        advanced_lines = [f"🧠 Advanced risk: {advanced.risk_level}", f"📚 Evidence window: {advanced.evidence_coverage:.0%}"]
        if advanced.warnings:
            advanced_lines.append("⚠️ Advanced warnings: " + ", ".join(advanced.warnings))
        sections.append(
            f"🔬 {qualification.symbol} · MATURE RESEARCH\n"
            + format_advanced_section(report)
            + "\n"
            + "\n".join(advanced_lines)
        )
    sections.append("🧭 FINAL NOTE\n────────────────────\nResearch every core-qualified and mature-qualified token yourself before taking any action")
    return "\n\n".join(sections)


def main() -> None:
    limit = int(os.getenv("OBSERVATION_LIMIT", "30"))
    scan = scan_tokens(limit=limit)
    send_telegram(build_message(scan))
    print(
        "Telegram scan report sent; "
        f"discovered={scan.discovered}; core_qualified={scan.core_qualified}; "
        f"advanced_evaluated={scan.advanced_evaluated}; qualified={len(scan.qualified)}; execution=disabled"
    )


if __name__ == "__main__":
    main()
