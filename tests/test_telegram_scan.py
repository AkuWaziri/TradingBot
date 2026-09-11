from types import SimpleNamespace

from telegram_scan import _telegram_chunks, format_scan_status


def test_telegram_chunks_respect_safe_limit():
    text = "\n\n".join(["section " + ("x" * 900) for _ in range(6)])
    chunks = _telegram_chunks(text, limit=1000)

    assert len(chunks) > 1
    assert all(len(chunk) <= 1000 for chunk in chunks)
    assert "section " in chunks[0]


def test_scan_status_exposes_mature_pipeline():
    scan = SimpleNamespace(
        discovered=10,
        requested=10,
        market_data_available=10,
        evaluated=8,
        core_qualified=4,
        advanced_evaluated=4,
        qualified=(1, 2),
        rejection_reasons=(("advanced_single_wallet_flow_concentration_too_high", 2),),
    )

    message = format_scan_status(scan)

    assert "🧠 Mature qualification: core gates + advanced risk gates" in message
    assert "🧪 Core-qualified: 4" in message
    assert "🔬 Advanced evaluated: 4" in message
    assert "🟢 Mature qualified: 2" in message
