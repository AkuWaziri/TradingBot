"""Read-only Helius adapter for Solana token intelligence.

No wallet, signer, transaction builder, or transaction submission exists here.
The adapter only reads indexed/on-chain state used by the trading brain.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from math import isfinite
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class HeliusOnchainError(RuntimeError):
    """Raised when Helius cannot return a valid on-chain observation."""


@dataclass(frozen=True)
class TokenAccountShare:
    address: str
    raw_amount: int
    decimals: int
    ui_amount: float | None
    owner: str | None = None

    @property
    def fraction_of_supply(self) -> float | None:
        return None


@dataclass(frozen=True)
class SolanaTokenState:
    mint: str
    symbol: str | None
    name: str | None
    supply_raw: int | None
    decimals: int | None
    token_program: str | None
    mint_authority: str | None
    freeze_authority: str | None
    price_usd: float | None
    top_accounts: tuple[TokenAccountShare, ...]
    indexed_slot: int | None

    def validate(self) -> None:
        if not self.mint.strip():
            raise ValueError("mint is required")
        if self.supply_raw is not None and self.supply_raw < 0:
            raise ValueError("supply_raw cannot be negative")
        if self.decimals is not None and not 0 <= self.decimals <= 255:
            raise ValueError("decimals is invalid")
        if self.price_usd is not None and (not isfinite(self.price_usd) or self.price_usd <= 0):
            raise ValueError("price_usd must be positive and finite")
        if self.indexed_slot is not None and self.indexed_slot < 0:
            raise ValueError("indexed_slot cannot be negative")

        for account in self.top_accounts:
            if not account.address or account.raw_amount < 0:
                raise ValueError("invalid token account")
            if account.owner is not None and not account.owner.strip():
                raise ValueError("invalid token account owner")
            if account.ui_amount is not None and (not isfinite(account.ui_amount) or account.ui_amount < 0):
                raise ValueError("invalid token account UI amount")


class HeliusProvider:
    """Read-only Helius DAS/RPC client for Solana token observations."""

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None, timeout: float = 10.0) -> None:
        self.api_key = api_key if api_key is not None else os.getenv("HELIUS_API_KEY")
        self.base_url = (base_url or os.getenv("HELIUS_RPC_BASE_URL", "https://mainnet.helius-rpc.com")).rstrip("/")
        self.timeout = timeout

    def _rpc(self, method: str, params: Any) -> Any:
        if not self.api_key:
            raise HeliusOnchainError("HELIUS_API_KEY is not configured")
        if not self.base_url.startswith("https://"):
            raise HeliusOnchainError("Helius RPC URL must use HTTPS")

        body = json.dumps({"jsonrpc": "2.0", "id": "trading-bot", "method": method, "params": params}).encode("utf-8")
        request = Request(
            f"{self.base_url}/?api-key={self.api_key}",
            data=body,
            method="POST",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                response_body = exc.read().decode("utf-8", errors="replace").strip()
            except OSError:
                response_body = ""
            if self.api_key:
                response_body = response_body.replace(self.api_key, "<redacted>")
            detail = response_body[:500] if response_body else exc.reason
            raise HeliusOnchainError(f"Helius HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HeliusOnchainError(f"Helius request failed: {exc}") from exc

        if not isinstance(payload, dict):
            raise HeliusOnchainError("Helius response is not an object")
        if payload.get("error") is not None:
            raise HeliusOnchainError(f"Helius RPC error: {payload['error']}")
        if "result" not in payload:
            raise HeliusOnchainError("Helius response has no result")
        return payload["result"]

    @staticmethod
    def _int(value: Any, field: str) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            raise HeliusOnchainError(f"invalid {field}")
        try:
            result = int(value)
        except (TypeError, ValueError) as exc:
            raise HeliusOnchainError(f"invalid {field}") from exc
        if result < 0:
            raise HeliusOnchainError(f"invalid {field}")
        return result

    @staticmethod
    def _float(value: Any, field: str) -> float | None:
        if value is None:
            return None
        try:
            result = float(value)
        except (TypeError, ValueError) as exc:
            raise HeliusOnchainError(f"invalid {field}") from exc
        if not isfinite(result) or result < 0:
            raise HeliusOnchainError(f"invalid {field}")
        return result

    def get_asset(self, mint: str) -> dict[str, Any]:
        mint = mint.strip()
        if not mint:
            raise ValueError("mint is required")
        result = self._rpc(
            "getAsset",
            {
                "id": mint,
                "displayOptions": {"showFungible": True},
            },
        )
        if not isinstance(result, dict):
            raise HeliusOnchainError("getAsset result is not an object")
        return result

    def get_recent_signatures(self, address: str, *, limit: int = 25) -> list[dict[str, Any]]:
        """Return recent confirmed signatures for a Solana program/account."""
        address = address.strip()
        if not address:
            raise ValueError("address is required")
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        result = self._rpc(
            "getSignaturesForAddress",
            [address, {"limit": limit, "commitment": "confirmed"}],
        )
        if not isinstance(result, list):
            raise HeliusOnchainError("invalid getSignaturesForAddress result")
        return [item for item in result if isinstance(item, dict)]

    def get_transaction(self, signature: str) -> dict[str, Any] | None:
        """Return one parsed transaction, or None when it is not yet available."""
        signature = signature.strip()
        if not signature:
            raise ValueError("signature is required")
        result = self._rpc(
            "getTransaction",
            [signature, {"encoding": "jsonParsed", "commitment": "confirmed", "maxSupportedTransactionVersion": 0}],
        )
        if result is None:
            return None
        if not isinstance(result, dict):
            raise HeliusOnchainError("invalid getTransaction result")
        return result

    def get_largest_accounts(self, mint: str) -> list[TokenAccountShare]:
        mint = mint.strip()
        if not mint:
            raise ValueError("mint is required")
        result = self._rpc("getTokenLargestAccounts", [mint])
        if not isinstance(result, dict) or not isinstance(result.get("value"), list):
            raise HeliusOnchainError("invalid getTokenLargestAccounts result")

        accounts: list[TokenAccountShare] = []
        for item in result["value"]:
            if not isinstance(item, dict):
                continue
            address = str(item.get("address") or "").strip()
            if not address:
                continue
            raw = self._int(item.get("amount"), "token account amount")
            decimals = self._int(item.get("decimals"), "token account decimals")
            if raw is None or decimals is None or decimals > 255:
                raise HeliusOnchainError("invalid token account balance")
            accounts.append(
                TokenAccountShare(
                    address=address,
                    raw_amount=raw,
                    decimals=decimals,
                    ui_amount=self._float(item.get("uiAmount"), "token account UI amount"),
                )
            )
        return accounts

    def get_token_account_owners(self, accounts: list[TokenAccountShare], mint: str) -> list[TokenAccountShare]:
        """Resolve token-account owners so concentration is measured by wallet, not token account."""
        if not accounts:
            return []
        mint = mint.strip()
        if not mint:
            raise ValueError("mint is required")

        addresses = [account.address for account in accounts]
        if len(addresses) > 100:
            raise HeliusOnchainError("too many token accounts for one owner-resolution request")

        result = self._rpc(
            "getMultipleAccounts",
            [addresses, {"encoding": "jsonParsed", "commitment": "finalized"}],
        )
        if not isinstance(result, dict) or not isinstance(result.get("value"), list):
            raise HeliusOnchainError("invalid getMultipleAccounts result")
        values = result["value"]
        if len(values) != len(accounts):
            raise HeliusOnchainError("owner-resolution result length mismatch")

        resolved: list[TokenAccountShare] = []
        for account, item in zip(accounts, values):
            if not isinstance(item, dict):
                raise HeliusOnchainError(f"token account not found: {account.address}")
            data = item.get("data")
            parsed = data.get("parsed") if isinstance(data, dict) else None
            info = parsed.get("info") if isinstance(parsed, dict) else None
            owner = str(info.get("owner") or "").strip() if isinstance(info, dict) else ""
            account_mint = str(info.get("mint") or "").strip() if isinstance(info, dict) else ""
            if not owner:
                raise HeliusOnchainError(f"owner unavailable for token account: {account.address}")
            if account_mint and account_mint != mint:
                raise HeliusOnchainError(f"token account mint mismatch: {account.address}")
            resolved.append(
                TokenAccountShare(
                    address=account.address,
                    raw_amount=account.raw_amount,
                    decimals=account.decimals,
                    ui_amount=account.ui_amount,
                    owner=owner,
                )
            )
        return resolved

    def get_supply(self, mint: str) -> tuple[int, int]:
        mint = mint.strip()
        if not mint:
            raise ValueError("mint is required")
        result = self._rpc("getTokenSupply", [mint])
        if not isinstance(result, dict) or not isinstance(result.get("value"), dict):
            raise HeliusOnchainError("invalid getTokenSupply result")
        value = result["value"]
        raw = self._int(value.get("amount"), "token supply")
        decimals = self._int(value.get("decimals"), "token supply decimals")
        if raw is None or decimals is None or decimals > 255:
            raise HeliusOnchainError("invalid token supply")
        return raw, decimals

    def inspect_token(self, mint: str) -> SolanaTokenState:
        asset = self.get_asset(mint)
        supply_raw: int | None = None
        decimals: int | None = None
        token_program: str | None = None
        mint_authority: str | None = None
        freeze_authority: str | None = None
        price_usd: float | None = None

        token_info = asset.get("token_info")
        if isinstance(token_info, dict):
            supply_raw = self._int(token_info.get("supply"), "asset token supply")
            decimals = self._int(token_info.get("decimals"), "asset token decimals")
            token_program = str(token_info.get("token_program") or "").strip() or None
            mint_authority = str(token_info.get("mint_authority") or "").strip() or None
            freeze_authority = str(token_info.get("freeze_authority") or "").strip() or None
            price_info = token_info.get("price_info")
            if isinstance(price_info, dict):
                price_usd = self._float(price_info.get("price_per_token"), "asset token price")

        if supply_raw is None or decimals is None:
            supply_raw, decimals = self.get_supply(mint)

        content = asset.get("content") if isinstance(asset.get("content"), dict) else {}
        metadata = content.get("metadata") if isinstance(content.get("metadata"), dict) else {}
        symbol = str(metadata.get("symbol") or "").strip() or None
        name = str(metadata.get("name") or "").strip() or None
        indexed_slot = self._int(asset.get("last_indexed_slot"), "last indexed slot")
        top_accounts = self.get_largest_accounts(mint)
        top_accounts = self.get_token_account_owners(top_accounts, mint)

        state = SolanaTokenState(
            mint=mint,
            symbol=symbol,
            name=name,
            supply_raw=supply_raw,
            decimals=decimals,
            token_program=token_program,
            mint_authority=mint_authority,
            freeze_authority=freeze_authority,
            price_usd=price_usd,
            top_accounts=tuple(top_accounts),
            indexed_slot=indexed_slot,
        )
        state.validate()
        return state
