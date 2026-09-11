import json

import pytest

from ethereum_rpc import EthereumRPCClient, EthereumRPCResponseError


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_chain_id_decodes_hex(monkeypatch):
    def fake_urlopen(request, timeout):
        return FakeResponse({"jsonrpc": "2.0", "id": 1, "result": "0x1"})

    monkeypatch.setattr("ethereum_rpc.urllib.request.urlopen", fake_urlopen)
    client = EthereumRPCClient("https://example.invalid")
    assert client.chain_id() == 1


def test_successful_call_is_cached(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(1)
        return FakeResponse({"jsonrpc": "2.0", "id": 1, "result": "0x123"})

    monkeypatch.setattr("ethereum_rpc.urllib.request.urlopen", fake_urlopen)
    client = EthereumRPCClient("https://example.invalid", cache_ttl_seconds=60)
    assert client.get_block_number() == 0x123
    assert client.get_block_number() == 0x123
    assert len(calls) == 1


def test_rpc_error_is_not_treated_as_safe(monkeypatch):
    def fake_urlopen(request, timeout):
        return FakeResponse({"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "failure"}})

    monkeypatch.setattr("ethereum_rpc.urllib.request.urlopen", fake_urlopen)
    client = EthereumRPCClient("https://example.invalid")
    with pytest.raises(EthereumRPCResponseError):
        client.get_block_number()


def test_execution_methods_are_forbidden():
    client = EthereumRPCClient("https://example.invalid")
    with pytest.raises(ValueError, match="forbidden"):
        client.call("eth_sendRawTransaction", ["0xdead"])


def test_get_logs_requires_list_result(monkeypatch):
    def fake_urlopen(request, timeout):
        return FakeResponse({"jsonrpc": "2.0", "id": 1, "result": {}})

    monkeypatch.setattr("ethereum_rpc.urllib.request.urlopen", fake_urlopen)
    client = EthereumRPCClient("https://example.invalid")
    with pytest.raises(EthereumRPCResponseError, match="non-list"):
        client.get_logs({})
