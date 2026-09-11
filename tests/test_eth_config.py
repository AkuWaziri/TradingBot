import pytest

from eth_config import EthereumConfig


def test_ethereum_config_accepts_mainnet_defaults(monkeypatch):
    config = EthereumConfig(rpc_url="https://example.invalid")
    config.validate()


def test_ethereum_config_rejects_non_mainnet():
    config = EthereumConfig(chain_id=137, rpc_url="https://example.invalid")
    with pytest.raises(ValueError, match="chain_id"):
        config.validate()


def test_ethereum_config_rejects_missing_rpc_url():
    config = EthereumConfig(rpc_url="")
    with pytest.raises(ValueError, match="ETH_RPC_URL"):
        config.validate()
