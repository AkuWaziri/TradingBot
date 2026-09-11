# TradingBot

A **read-only Solana token intelligence and qualification system** for research.

The project discovers newly active Solana tokens, validates market and on-chain conditions, applies deterministic qualification gates, and reports mature-qualified candidates to Telegram.

**There is no auto-trading, wallet signing, transaction submission, or execution path. Manual trading only.**

## Current stage

The system now uses a two-stage qualification pipeline:

### Stage 1 — Core qualification

The established deterministic core evaluates:

- Solana market identity
- liquidity
- liquidity / market-cap relationship
- recent 5-minute volume
- 5-minute buy/sell pressure
- 5-minute momentum
- 1-hour momentum
- token age
- mint and freeze authority safety
- wallet-level holder concentration
- market-cap and pair-age bounds
- extreme negative 5-minute momentum rejection

The core score remains **0–100**, with eight equally weighted checks at 12.5 points each. Hard safety failures cannot be compensated by score.

### Stage 2 — Advanced risk qualification

A core pass is not a final qualification. The system then performs bounded, cached Helius transaction analysis for:

- early-buyer behavior
- possible common-funder / related-wallet clusters
- creator/deployer behavior
- buyer participation growth
- buy-flow growth
- trader diversity
- wallet trade concentration
- wallet flow concentration
- repeated-wallet activity
- one-sided observed flow
- transaction evidence completeness

Advanced signals are separated into **hard risk gates** and **research warnings**. Possible coordination is never treated as proof merely because wallets share a funding source.

The advanced layer is fail-closed when evidence is insufficient or materially incomplete.

## Qualification principle

The system does not treat a high score as proof that a token is safe.

The decision path is:

```text
Discovery
   ↓
Market data
   ↓
Token / authority safety
   ↓
Holder concentration
   ↓
Core qualification
   ↓
Advanced transaction intelligence
   ↓
Evidence-quality gate
   ↓
Advanced risk gates
   ↓
MATURE QUALIFIED
   ↓
Telegram
```

Research heuristics remain warnings until there is enough evidence to justify a deterministic hard gate. Thresholds should be calibrated against observed outcomes rather than promoted simply because a metric looks suspicious.

## Data and safety rules

- Solana mint address is the canonical token identity.
- Discovery sources are inputs, not separate qualification systems.
- Helius responses are cached within a scan to reduce duplicate requests and rate-limit pressure.
- Transaction windows are bounded for predictable cost and runtime.
- Missing or materially incomplete evidence fails closed for final qualification.
- Telegram is reporting only.
- No private key, wallet, signer, or transaction-execution dependency is required.
- Secrets must never be committed to GitHub.

## Telegram output

Telegram reports expose the complete pipeline state:

- candidates discovered
- market data available
- core evaluations
- core-qualified candidates
- advanced evaluations
- mature-qualified candidates
- rejection reasons
- contract address (CA)
- market/liquidity data
- momentum and flow
- advanced risk and evidence coverage

Long reports are split safely so Telegram's message-length limit cannot silently break delivery.

## Testing

The repository uses deterministic unit tests for the qualification, on-chain intelligence, discovery, advanced intelligence, mature advanced-risk gates, and Telegram reporting layers.

GitHub Actions runs the test suite on pushes and pull requests, with manual dispatch available.

Local:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pytest -q
```

## Research standard

External research is used as input to system design, not as unquestioned truth. The implementation is expected to follow this cycle:

```text
Research
  ↓
Implement
  ↓
Test on real observations
  ↓
Measure false positives / false negatives
  ↓
Calibrate thresholds
  ↓
Promote reliable signals into qualification
```

A token shown as mature-qualified means it passed the **current validated screening stack**. It is not a guarantee of safety, profitability, or future performance.

## Execution status

```text
mode=read-only
execution=disabled
manual_trading_only=true
auto_trading=false
```
