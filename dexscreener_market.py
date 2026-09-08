"""Read-only DexScreener market data for Solana token candidates.

This module never signs, submits, or simulates a transaction. It only normalizes
public market observations for the strategy layer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from live_market import LiveMarketError, _get_json, _optional_float


@dataclass(frozen=True)
class DexScreenerPair:
    chain_id: str
    dex_id: str
    pair_address: str
    base_token_address: str
    base_token_symbol: str
    base_token_name: str
    quote_token_address: str
    quote_token_symbol: str
    price_usd: float | None
    liquidity_usd: float | None
    market_cap_usd: float | None
    fdv_usd: float | None
    price_change_5m_pct: float | None
    price_change_1h_pct: float | None
    price_change_6h_pct: float | None
    price_change_24h_pct: float | None
    volume_5m_usd: float | None
    volume_1h_usd: float | None
    volume_6h_usd: float | None
    volume_24h_usd: float | None
    buys_5m: int | None
    sells_5m: int | None
    buys_1h: int | None
    sells_1h: int | None
    buys_6h: int | None
    sells_6h: int | None
    buys_24h: int | None
    sells_24h: int | None
    pair_created_at: datetime | None
    url: str | None
    source: str = "dexscreener"

    def validate(self) -> None:
        if self.chain_id != "solana":
            raise ValueError("only Solana pairs are supported")
        required = (
            self.pair_address,
            self.base_token_address,
            self.base_token_symbol,
            self.quote_token_address,
            self.quote_token_symbol,
        )
        if any(not value.strip() for value in required):
            raise ValueError("pair and token identifiers are required")

        for name in (
            "price_usd", "liquidity_usd", "market_cap_usd", "fdv_usd",
            "price_change_5m_pct", "price_change_1h_pct", "price_change_6h_pct",
            "price_change_24h_pct", "volume_5m_usd", "volume_1h_usd",
            "volume_6h_usd", "volume_24h_usd",
        ):
            value = getattr(self, name)
            if value is not None and not isfinite(value):
                raise ValueError(f"{name} must be finite")
            if name not in {"price_change_5m_pct", "price_change_1h_pct", "price_change_6h_pct", "price_change_24h_pct"} and value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.price_usd is not None and self.price_usd <= 0:
            raise ValueError("price_usd must be positive")

        for name in (
            "buys_5m", "sells_5m", "buys_1h", "sells_1h",
            "buys_6h", "sells_6h", "buys_24h", "sells_24h",
        ):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
                raise ValueError(f"{name} must be a non-negative integer")

        if self.pair_created_at is not None and self.pair_created_at.tzinfo is None:
            raise ValueError("pair_created_at must be timezone-aware")


class DexScreenerProvider:
    """Read-only adapter for DexScreener's public Solana token endpoints."""

    _MAX_TOKEN_ADDRESSES = 30

    def __init__(self, *, base_url: str | None = None, timeout: float = 10.0) -> None:
        self.base_url = (
            base_url or os.getenv("DEXSCREENER_API_BASE_URL", "https://api.dexscreener.com")
        ).rstrip("/")
        self.timeout = timeout

    @staticmethod
    def _count(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            raise LiveMarketError("invalid DexScreener transaction count")
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise LiveMarketError("invalid DexScreener transaction count") from exc
        if number < 0 or (isinstance(value, float) and value != number):
            raise LiveMarketError("invalid DexScreener transaction count")
        return number

    @staticmethod
    def _created_at(value: Any) -> datetime | None:
        if value is None:
            return None
        try:
            timestamp = float(value)
            if timestamp > 10_000_000_000:
                timestamp /= 1000
            created = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (TypeError, ValueError, OSError, OverflowError) as exc:
            raise LiveMarketError("invalid DexScreener pair timestamp") from exc
        if created > datetime.now(timezone.utc):
            raise LiveMarketError("DexScreener pair timestamp is in the future")
        return created

    def _parse_pair(self, item: Any) -> DexScreenerPair | None:
        if not isinstance(item, dict):
            return None
        if item.get("chainId") != "solana":
            return None
        base = item.get("baseToken")
        quote = item.get("quoteToken")
        if not isinstance(base, dict) or not isinstance(quote, dict):
            return None

        txns = item.get("txns") or {}
        volume = item.get("volume") or {}
        change = item.get("priceChange") or {}
        if not isinstance(txns, dict) or not isinstance(volume, dict) or not isinstance(change, dict):
            raise LiveMarketError("malformed DexScreener market fields")

        def counts(window: str) -> tuple[int | None, int | None]:
            data = txns.get(window) or {}
            if not isinstance(data, dict):
                raise LiveMarketError("malformed DexScreener transaction window")
            return self._count(data.get("buys")), self._count(data.get("sells"))

        b5, s5 = counts("m5")
        b1, s1 = counts("h1")
        b6, s6 = counts("h6")
        b24, s24 = counts("h24")

        pair = DexScreenerPair(
            chain_id="solana",
            dex_id=str(item.get("dexId") or "").strip(),
            pair_address=str(item.get("pairAddress") or "").strip(),
            base_token_address=str(base.get("address") or "").strip(),
            base_token_symbol=str(base.get("symbol") or "").strip(),
            base_token_name=str(base.get("name") or "").strip(),
            quote_token_address=str(quote.get("address") or "").strip(),
            quote_token_symbol=str(quote.get("symbol") or "").strip(),
            price_usd=_optional_float(item.get("priceUsd")),
            liquidity_usd=_optional_float((item.get("liquidity") or {}).get("usd")),
            market_cap_usd=_optional_float(item.get("marketCap")),
            fdv_usd=_optional_float(item.get("fdv")),
            price_change_5m_pct=_optional_float(change.get("m5")),
            price_change_1h_pct=_optional_float(change.get("h1")),
            price_change_6h_pct=_optional_float(change.get("h6")),
            price_change_24h_pct=_optional_float(change.get("h24")),
            volume_5m_usd=_optional_float(volume.get("m5")),
            volume_1h_usd=_optional_float(volume.get("h1")),
            volume_6h_usd=_optional_float(volume.get("h6")),
            volume_24h_usd=_optional_float(volume.get("h24")),
            buys_5m=b5, sells_5m=s5, buys_1h=b1, sells_1h=s1,
            buys_6h=b6, sells_6h=s6, buys_24h=b24, sells_24h=s24,
            pair_created_at=self._created_at(item.get("pairCreatedAt")),
            url=str(item.get("url") or "").strip() or None,
        )
        try:
            pair.validate()
        except ValueError as exc:
            raise LiveMarketError(str(exc)) from exc
        return pair

    def pairs_by_tokens(self, token_addresses: list[str]) -> list[DexScreenerPair]:
        addresses = list(dict.fromkeys(address.strip() for address in token_addresses if address and address.strip()))
        if not addresses:
            return []
        if len(addresses) > self._MAX_TOKEN_ADDRESSES:
            raise ValueError("DexScreener accepts at most 30 token addresses per request")

        path = "/tokens/v1/solana/" + ",".join(addresses)
        payload = _get_json(f"{self.base_url}{path}", timeout=self.timeout)
        if not isinstance(payload, list):
            raise LiveMarketError("DexScreener token response is not a list")

        pairs: list[DexScreenerPair] = []
        for item in payload:
            pair = self._parse_pair(item)
            if pair is not None:
                pairs.append(pair)
        return pairs

    def pairs_by_token(self, token_address: str) -> list[DexScreenerPair]:
        token_address = token_address.strip()
        if not token_address:
            raise ValueError("token_address is required")
        payload = _get_json(
            f"{self.base_url}/token-pairs/v1/solana/{token_address}",
            timeout=self.timeout,
        )
        if not isinstance(payload, list):
            raise LiveMarketError("DexScreener pair response is not a list")
        pairs: list[DexScreenerPair] = []
        for item in payload:
            pair = self._parse_pair(item)
            if pair is not None:
                pairs.append(pair)
        return pairs
