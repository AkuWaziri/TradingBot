# TradingBot

A test-first trading bot project. **Paper trading is the default. Live trading is not implemented yet.**

## Current stage

This first version establishes the core safety and testing layer:

- Configuration through environment variables
- Baseline moving-average strategy
- Position-size risk limit
- Paper execution engine
- Unit tests
- GitHub Actions CI

The moving-average strategy is a deterministic baseline for validating the engine. It is **not** presented as a profitable strategy.

## Safety rule

The project must be tested with historical/synthetic data and paper execution before any real-money execution is considered. Exchange credentials must never be committed to GitHub.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
pytest -q
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

## Configuration

`TRADING_MODE` defaults to `paper`.

Other settings control the symbol, starting balance, maximum position size, and strategy windows.

## Next build stage

1. Add market-data interface.
2. Add historical/synthetic dataset runner.
3. Build backtesting engine with fees and performance metrics.
4. Run strategy tests and backtests in GitHub Actions.
5. Add paper-trading loop.
6. Only after validation, evaluate an exchange adapter for live execution.
