"""Small, read-only Ethereum JSON-RPC client with bounded in-memory caching.

No signing, account management, transaction submission, or private-key handling
exists in this module by design.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class EthereumRPCError(RuntimeError):
    """Base error for Ethereum RPC failures."""


class EthereumRPCProviderError(EthereumRPCError):
    """Provider/network/HTTP failure."""


class EthereumRPCResponseError(EthereumRPCError):
    """JSON-RPC returned an error response."""


@dataclass(frozen=True)
class CacheEntry:
    expires_at: float
    value: Any


class EthereumRPCClient:
    """Read-only JSON-RPC client for Ethereum mainnet."""

    def __init__(self, rpc_url: str, timeout_seconds: float = 15.0, cache_ttl_seconds: int = 30) -> None:
        if not rpc_url.strip():
            raise ValueError("rpc_url is required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if cache_ttl_seconds < 0:
            raise ValueError("cache_ttl_seconds cannot be negative")
        self.rpc_url = rpc_url
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, CacheEntry] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _cache_key(method: str, params: list[Any]) -> str:
        payload = json.dumps([method, params], sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _get_cached(self, key: str) -> Any | None:
        if self.cache_ttl_seconds == 0:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._cache.pop(key, None)
                return None
            return entry.value

    def _set_cached(self, key: str, value: Any) -> None:
        if self.cache_ttl_seconds == 0:
            return
        with self._lock:
            self._cache[key] = CacheEntry(time.monotonic() + self.cache_ttl_seconds, value)

    def call(self, method: str, params: list[Any] | None = None, *, use_cache: bool = True) -> Any:
        if not method or method.startswith("eth_send") or method in {
            "personal_sign",
            "eth_sign",
            "eth_signTransaction",
            "eth_sendRawTransaction",
        }:
            raise ValueError("Execution/signing RPC methods are forbidden")

        params = [] if params is None else params
        key = self._cache_key(method, params)
        if use_cache:
            cached = self._get_cached(key)
            if cached is not None:
                return cached

        payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode("utf-8")
        request = urllib.request.Request(
            self.rpc_url,
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
            raise EthereumRPCProviderError(f"Ethereum RPC request failed: {exc}") from exc

        try:
            result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise EthereumRPCProviderError("Ethereum RPC returned invalid JSON") from exc

        if "error" in result:
            raise EthereumRPCResponseError(str(result["error"]))
        if "result" not in result:
            raise EthereumRPCResponseError("Ethereum RPC response missing result")

        value = result["result"]
        if use_cache:
            self._set_cached(key, value)
        return value

    def chain_id(self) -> int:
        value = self.call("eth_chainId")
        return int(value, 16)

    def get_block_number(self) -> int:
        value = self.call("eth_blockNumber")
        return int(value, 16)

    def get_code(self, address: str, block: str = "latest") -> str:
        return self.call("eth_getCode", [address, block])

    def get_transaction(self, tx_hash: str) -> Any:
        return self.call("eth_getTransactionByHash", [tx_hash])

    def get_transaction_receipt(self, tx_hash: str) -> Any:
        return self.call("eth_getTransactionReceipt", [tx_hash])

    def get_logs(self, filter_params: dict[str, Any], *, use_cache: bool = True) -> list[Any]:
        result = self.call("eth_getLogs", [filter_params], use_cache=use_cache)
        if not isinstance(result, list):
            raise EthereumRPCResponseError("eth_getLogs returned a non-list result")
        return result
