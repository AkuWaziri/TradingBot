"""Configuration for the Ethereum read-only intelligence system.

This module is intentionally separate from the existing trading/Solana
configuration. It contains no execution or wallet configuration.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class EthereumConfig:
    chain_id: int = int(os.getenv("ETH_CHAIN_ID", "1"))
    rpc_url: str = os.getenv("ETH_RPC_URL", "")
    observation_limit: int = int(os.getenv("ETH_OBSERVATION_LIMIT", "25"))
    rpc_timeout_seconds: float = float(os.getenv("ETH_RPC_TIMEOUT_SECONDS", "15"))
    rpc_cache_ttl_seconds: int = int(os.getenv("ETH_RPC_CACHE_TTL_SECONDS", "30"))
    core_threshold: float = float(os.getenv("ETH_CORE_THRESHOLD", "75"))
    telegram_interval_minutes: int = int(os.getenv("ETH_TELEGRAM_INTERVAL_MINUTES", "15"))

    def validate(self) -> None:
        if self.chain_id != 1:
            raise ValueError("ETH_CHAIN_ID must be 1 for the initial Ethereum mainnet system")
        if not self.rpc_url.strip():
            raise ValueError("ETH_RPC_URL is required")
        if self.observation_limit <= 0:
            raise ValueError("ETH_OBSERVATION_LIMIT must be positive")
        if self.rpc_timeout_seconds <= 0:
            raise ValueError("ETH_RPC_TIMEOUT_SECONDS must be positive")
        if self.rpc_cache_ttl_seconds < 0:
            raise ValueError("ETH_RPC_CACHE_TTL_SECONDS cannot be negative")
        if not 0 <= self.core_threshold <= 100:
            raise ValueError("ETH_CORE_THRESHOLD must be between 0 and 100")
        if self.telegram_interval_minutes <= 0:
            raise ValueError("ETH_TELEGRAM_INTERVAL_MINUTES must be positive")


eth_config = EthereumConfig()
