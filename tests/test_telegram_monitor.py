import pytest

from telegram_monitor import TelegramMonitorError, _telegram_send, build_message


def test_build_message_delegates_to_observation(monkeypatch):
    monkeypatch.setattr("telegram_monitor.run_observation", lambda *, limit: f"limit={limit}")
    assert build_message(7) == "limit=7"


def test_telegram_send_requires_credentials():
    with pytest.raises(TelegramMonitorError, match="required"):
        _telegram_send("", "", "hello")
