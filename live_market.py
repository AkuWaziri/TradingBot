"""Read-only live market adapters for observation/paper trading.

No adapter in this module can place an order or sign a transaction.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class LiveMarketError(RuntimeError):
    """Raised when a live market provider cannot return valid data."""


@dataclass(frozen=True)
class LiveToken:
    mint: str
    symbol: str
    name: str
    price_usd: float | None
    market_cap_usd: float | None
    volume_24h_usd: float | None
    price_change_24h_pct: float | None
    liquidity_usd: float | None
    created_at: datetime | None
    source: str

    def validate(self) -> None:
        if not self.mint or not self.symbol:
            raise ValueError("token mint and symbol are required")
        for field_name in (
            "price_usd",
            "market_cap_usd",
            "volume_24h_usd",
            "price_change_24h_pct",
            "liquidity_usd",
        ):
            value = getattr(self, field_name)
            if value is not None and not isfinite(value):
                raise ValueError(f"{field_name} must be finite")
            if field_name != "price_change_24h_pct" and value is not None and value < 0:
                raise ValueError(f"{field_name} cannot be negative")
        if self.price_usd is not None and self.price_usd <= 0:
            raise ValueError("price_usd must be positive")


def _get_json(url: str, *, headers: dict[str, str] | None = None, timeout: float = 10.0) -> Any:
    if not url.startswith("https://"):
        raise LiveMarketError("live provider URLs must use HTTPS")
    request = Request(url, method="GET", headers={"Accept": "application/json", **(headers or {})})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LiveMarketError(f"live provider request failed: {exc}") from exc


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise LiveMarketError(f"invalid numeric provider value: {value!r}") from exc
    return result if isfinite(result) else None


class PumpFunProvider:
    """Read-only Pump.fun token discovery using the current v3 API.

    Pump.fun's current frontend API requires authorization for these endpoints.
    The token is read from PUMP_API_TOKEN and is never logged.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_token: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("PUMP_API_BASE_URL", "https://frontend-api-v3.pump.fun")).rstrip("/")
        self.api_token = api_token if api_token is not None else os.getenv("PUMP_API_TOKEN")
        self.timeout = timeout

    def currently_live(self, *, limit: int = 20, offset: int = 0) -> list[LiveToken]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset cannot be negative")
        if not self.api_token:
            raise LiveMarketError("PUMP_API_TOKEN is not configured")

        query = urlencode({"limit": limit, "offset": offset, "includeNsfw": "false"})
        payload = _get_json(
            f"{self.base_url}/coins/currently-live?{query}",
            headers={"Authorization": f"Bearer {self.api_token}"},
            timeout=self.timeout,
        )
        if not isinstance(payload, list):
            raise LiveMarketError("Pump.fun currently-live response is not a list")

        tokens: list[LiveToken] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            mint = str(item.get("mint") or item.get("address") or "").strip()
            if not mint:
                continue
            created = item.get("created_timestamp")
            created_at = None
            if created is not None:
                try:
                    timestamp = float(created)
                    if timestamp > 10_000_000_000:
                        timestamp /= 1000
                    created_at = datetime.fromtimestamp(timestamp, tz=timezone.utc)
                except (TypeError, ValueError, OSError, OverflowError):
                    created_at = None
            token = LiveToken(
                mint=mint,
                symbol=str(item.get("symbol") or "").strip(),
                name=str(item.get("name") or "").strip(),
                price_usd=_optional_float(item.get("usd_market_cap") and None),
                market_cap_usd=_optional_float(item.get("usd_market_cap") or item.get("market_cap")),
                volume_24h_usd=_optional_float(item.get("volume_24h") or item.get("volume")),
                price_change_24h_pct=_optional_float(item.get("price_change_percentage_24h")),
                liquidity_usd=_optional_float(item.get("liquidity")),
                created_at=created_at,
                source="pump.fun",
            )
            try:
                token.validate()
            except ValueError:
                continue
            tokens.append(token)
        return tokens


class CoinGeckoProvider:
    """Read-only CoinGecko token-price cross-check for Solana tokens."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        platform: str = "solana",
        timeout: float = 10.0,
    ) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("COINGECKO_API_KEY")
        self.base_url = (base_url or os.getenv("COINGECKO_API_BASE_URL", "https://api.coingecko.com/api/v3")).rstrip("/")
        self.platform = platform
        self.timeout = timeout

    def prices_by_contracts(self, contracts: list[str]) -> dict[str, dict[str, float | None]]:
        contracts = [c.strip() for c in contracts if c and c.strip()]
        if not contracts:
            return {}
        if len(contracts) > 50:
            raise ValueError("CoinGecko contract lookup is limited to 50 addresses per request")
        if not self.api_key:
            raise LiveMarketError("COINGECKO_API_KEY is not configured")

        query = urlencode(
            {
                "contract_addresses": ",".join(contracts),
                "vs_currencies": "usd",
                "include_market_cap": "true",
                "include_24hr_vol": "true",
                "include_24hr_change": "true",
                "include_last_updated_at": "true",
            }
        )
        payload = _get_json(
            f"{self.base_url}/simple/token_price/{self.platform}?{query}",
            headers={"x-cg-demo-api-key": self.api_key},
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise LiveMarketError("CoinGecko response is not an object")

        result: dict[str, dict[str, float | None]] = {}
        for address, data in payload.items():
            if not isinstance(data, dict):
                continue
            result[str(address)] = {
                "price_usd": _optional_float(data.get("usd")),
                "market_cap_usd": _optional_float(data.get("usd_market_cap")),
                "volume_24h_usd": _optional_float(data.get("usd_24h_vol")),
                "price_change_24h_pct": _optional_float(data.get("usd_24h_change")),
                "last_updated_at": _optional_float(data.get("last_updated_at")),
            }
        return result

    def enrich(self, tokens: list[LiveToken]) -> list[LiveToken]:
        prices = self.prices_by_contracts([token.mint for token in tokens])
        enriched: list[LiveToken] = []
        for token in tokens:
            data = prices.get(token.mint, {})
            enriched.append(
                LiveToken(
                    mint=token.mint,
                    symbol=token.symbol,
                    name=token.name,
                    price_usd=data.get("price_usd"),
                    market_cap_usd=data.get("market_cap_usd") or token.market_cap_usd,
                    volume_24h_usd=data.get("volume_24h_usd") or token.volume_24h_usd,
                    price_change_24h_pct=data.get("price_change_24h_pct") or token.price_change_24h_pct,
                    liquidity_usd=token.liquidity_usd,
                    created_at=token.created_at,
                    source="pump.fun+coingecko" if data else token.source,
                )
            )
        return enriched
