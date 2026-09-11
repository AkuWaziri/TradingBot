"""Bounded per-scan Helius response caching for read-only analysis."""

from __future__ import annotations

from typing import Any

from helius_onchain import HeliusProvider


class CachedHeliusProvider:
    """Cache signatures and transactions while bounding the scan window."""

    def __init__(self, provider: HeliusProvider | None = None, signature_limit: int = 50) -> None:
        if signature_limit < 1:
            raise ValueError("signature_limit must be >= 1")
        self._provider = provider or HeliusProvider()
        self._signature_limit = signature_limit
        self._signatures: dict[str, list[dict[str, Any]]] = {}
        self._transactions: dict[str, dict[str, Any] | None] = {}

    @property
    def signature_limit(self) -> int:
        return self._signature_limit

    def get_recent_signatures(self, address: str, limit: int = 100) -> list[dict[str, Any]]:
        address = str(address).strip()
        bounded = min(limit, self._signature_limit)
        cached = self._signatures.get(address)
        if cached is None or len(cached) < bounded:
            self._signatures[address] = self._provider.get_recent_signatures(address, limit=bounded)
            cached = self._signatures[address]
        return cached[:bounded]

    def get_transaction(self, signature: str) -> dict[str, Any] | None:
        signature = str(signature).strip()
        if signature not in self._transactions:
            self._transactions[signature] = self._provider.get_transaction(signature)
        return self._transactions[signature]

    def __getattr__(self, name: str) -> Any:
        return getattr(self._provider, name)
