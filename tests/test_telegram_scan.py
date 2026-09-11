from types import SimpleNamespace

from qualified_monitor import summarize_rejections
from telegram_scan import _telegram_chunks, format_scan_status


def test_telegram_chunks_respect_safe_limit():
    text = "\n\n".join(["section " + ("x" * 900) for _ in range(6)])
    chunks = _telegram_chunks(text, limit=1000)

    assert len(chunks) > 1
    assert all(len(chunk) <= 1000 for chunk in chunks)
    assert "section " in chunks[0]


def test_rejections_are_separated_for_calibration():
    grouped = summarize_rejections((
        ("top_token_account_concentration_too_high", 4),
        ("advanced_transaction_data_too_incomplete", 2),
        ("helius_error", 3),
        ("data_validation_error", 1),
    ))

    assert grouped["risk_rejection"] == (("top_token_account_concentration_too_high", 4),)
    assert grouped["data_insufficient"] == (
        ("advanced_transaction_data_too_incomplete", 2),
        ("data_validation_error", 1),
    )
    assert grouped["provider_failure"] == (("helius_error", 3),)


def test_scan_status_exposes_mature_pipeline_and_failure_classes():
    scan = SimpleNamespace(
        discovered=10,
        requested=10,
        market_data_available=10,
        evaluated=8,
        core_qualified=4,
        advanced_evaluated=4,
        qualified=(1, 2),
        rejection_reasons=(
            ("advanced_single_wallet_flow_concentration_too_high", 2),
            ("advanced_transaction_data_too_incomplete", 1),
            ("helius_error", 3),
        ),
    )

    message = format_scan_status(scan)

    assert "🧠 Mature qualification: core gates + advanced risk gates" in message
    assert "🧪 Core-qualified: 4" in message
    assert "🔬 Advanced evaluated: 4" in message
    assert "🟢 Mature qualified: 2" in message
    assert "🔴 Risk rejected:" in message
    assert "⚫ Data insufficient:" in message
    assert "🟠 Provider / technical failure:" in message
    assert "Evidence coverage" not in message
