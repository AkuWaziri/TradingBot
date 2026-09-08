import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    trading_mode: str = os.getenv("TRADING_MODE", "paper").lower()
    symbol: str = os.getenv("SYMBOL", "BTCUSDT")
    initial_balance: float = float(os.getenv("INITIAL_BALANCE", "10"))
    max_position_pct: float = float(os.getenv("MAX_POSITION_PCT", "0.02"))
    max_total_exposure_pct: float = float(os.getenv("MAX_TOTAL_EXPOSURE_PCT", "0.20"))
    max_daily_loss_pct: float = float(os.getenv("MAX_DAILY_LOSS_PCT", "0.02"))
    max_entries_per_token: int = int(os.getenv("MAX_ENTRIES_PER_TOKEN", "2"))
    fast_window: int = int(os.getenv("FAST_WINDOW", "5"))
    slow_window: int = int(os.getenv("SLOW_WINDOW", "20"))

    def validate(self) -> None:
        if self.trading_mode not in {"paper", "live"}:
            raise ValueError("TRADING_MODE must be 'paper' or 'live'")
        if self.initial_balance <= 0:
            raise ValueError("INITIAL_BALANCE must be positive")
        if not 0 < self.max_position_pct <= 1:
            raise ValueError("MAX_POSITION_PCT must be between 0 and 1")
        if not 0 < self.max_total_exposure_pct <= 1:
            raise ValueError("MAX_TOTAL_EXPOSURE_PCT must be between 0 and 1")
        if not 0 < self.max_daily_loss_pct < 1:
            raise ValueError("MAX_DAILY_LOSS_PCT must be between 0 and 1")
        if self.max_total_exposure_pct < self.max_position_pct:
            raise ValueError("MAX_TOTAL_EXPOSURE_PCT must be >= MAX_POSITION_PCT")
        if self.max_entries_per_token <= 0:
            raise ValueError("MAX_ENTRIES_PER_TOKEN must be positive")
        if self.fast_window <= 0 or self.slow_window <= 0:
            raise ValueError("Moving-average windows must be positive")
        if self.fast_window >= self.slow_window:
            raise ValueError("FAST_WINDOW must be smaller than SLOW_WINDOW")


config = Config()
config.validate()
