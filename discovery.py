"""Read-only Solana candidate discovery.

Discovery is deliberately separated from qualification. Every mint returned here
must still pass the same market, on-chain, safety, and qualification pipeline.
No wallet, signer, transaction builder, or trade execution exists here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dexscreener_market import DexScreenerProvider
from helius_onchain import HeliusOnchainError, HeliusProvider


PUMP_PROGRAM_ID = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"


@dataclass(frozen=True)
class DiscoveredMint:
    mint: str
    sources: tuple[str, ...]


def _merge(items: list[DiscoveredMint], limit: int) -> list[DiscoveredMint]:
    merged: dict[str, set[str]] = {}
    for item in items:
        mint = item.mint.strip()
        if not mint:
            continue
        merged.setdefault(mint, set()).update(item.sources)
        if len(merged) >= limit and mint not in merged:
            break
    return [
        DiscoveredMint(mint=mint, sources=tuple(sorted(sources)))
        for mint, sources in merged.items()
    ][:limit]


def _instruction_accounts(instruction: dict[str, Any]) -> list[str]:
    accounts = instruction.get("accounts")
    if not isinstance(accounts, list):
        return []
    return [str(value).strip() for value in accounts if isinstance(value, str) and value.strip()]


def _extract_pump_create_mints(transaction: dict[str, Any]) -> list[str]:
    """Extract mint accounts from Pump create instructions in a parsed transaction."""
    result: list[str] = []
    message = transaction.get("transaction", {}).get("message", {})
    instructions = message.get("instructions", []) if isinstance(message, dict) else []
    if not isinstance(instructions, list):
        return result

    for instruction in instructions:
        if not isinstance(instruction, dict):
            continue
        program_id = str(instruction.get("programId") or "").strip()
        if program_id != PUMP_PROGRAM_ID:
            continue
        accounts = _instruction_accounts(instruction)
        if not accounts:
            continue

        # Pump's public create_v2 instruction documents the mint as account #1.
        # In Solana's zero-based account array this is index 0.
        # Require a recognizable create instruction so ordinary Pump buys/sells
        # are not treated as new candidates.
        parsed = instruction.get("parsed")
        instruction_type = ""
        if isinstance(parsed, dict):
            instruction_type = str(parsed.get("type") or parsed.get("instruction") or "").lower()
        data = str(instruction.get("data") or "").lower()
        if instruction_type and "create" not in instruction_type:
            continue
        if not instruction_type and data:
            # Custom compiled instructions do not expose the instruction name.
            # The transaction log check below is the secondary discriminator.
            logs = transaction.get("meta", {}).get("logMessages", [])
            if not isinstance(logs, list) or not any("instruction: create" in str(log).lower() for log in logs):
                continue
        mint = accounts[0]
        if mint not in result:
            result.append(mint)
    return result


def discover_pump_mints(helius: HeliusProvider, *, scan_limit: int = 25) -> list[DiscoveredMint]:
    """Discover recent Pump-program coin creations directly from Solana RPC."""
    signatures = helius.get_recent_signatures(PUMP_PROGRAM_ID, limit=scan_limit)
    discovered: list[DiscoveredMint] = []
    for item in signatures:
        signature = str(item.get("signature") or "").strip()
        if not signature or item.get("err") is not None:
            continue
        try:
            transaction = helius.get_transaction(signature)
        except HeliusOnchainError:
            continue
        if transaction is None:
            continue
        for mint in _extract_pump_create_mints(transaction):
            discovered.append(DiscoveredMint(mint=mint, sources=("pump_fun_onchain",)))
    return discovered


def discover_candidates(*, limit: int = 30, pump_scan_limit: int = 25) -> list[DiscoveredMint]:
    """Return deduplicated Solana candidate mints from multiple discovery sources."""
    if not 1 <= limit <= 30:
        raise ValueError("limit must be between 1 and 30")
    if not 1 <= pump_scan_limit <= 100:
        raise ValueError("pump_scan_limit must be between 1 and 100")

    helius = HeliusProvider()
    dex = DexScreenerProvider()
    discovered: list[DiscoveredMint] = []

    # Direct on-chain Pump discovery is first so fresh launches are not displaced
    # by the narrower DexScreener token-profile feed.
    try:
        discovered.extend(discover_pump_mints(helius, scan_limit=pump_scan_limit))
    except HeliusOnchainError:
        # DexScreener remains available as a secondary source. Qualification still
        # fails closed later when required Helius token intelligence is unavailable.
        pass

    try:
        dex_mints = dex.latest_solana_token_addresses(limit=limit)
        discovered.extend(
            DiscoveredMint(mint=mint, sources=("dexscreener",)) for mint in dex_mints
        )
    except Exception:
        # Discovery is best-effort; individual candidates are still validated later.
        pass

    return _merge(discovered, limit)
