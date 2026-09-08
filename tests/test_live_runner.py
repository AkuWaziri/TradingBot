import pytest

import live_runner


def test_runner_delegates_to_solana_observation(monkeypatch):
    calls = []

    def fake_observation(*, limit):
        calls.append(limit)
        return "SOLANA LIVE OBSERVATION\nmode=read-only; execution=disabled"

    monkeypatch.setattr(live_runner, "run_observation", fake_observation)

    output = live_runner.run_observation(limit=10)

    assert calls == [10]
    assert "SOLANA LIVE OBSERVATION" in output
    assert "execution=disabled" in output


def test_solana_observation_limit_is_bounded():
    from solana_observation import observe_tokens

    with pytest.raises(ValueError, match="limit must be between 1 and 30"):
        observe_tokens(limit=0)

    with pytest.raises(ValueError, match="limit must be between 1 and 30"):
        observe_tokens(limit=31)
