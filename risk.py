from dataclasses import dataclass
from math import isclose


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    quantity: float
    reason: str


def calculate_position_size(balance: float, price: float, max_position_pct: float) -> float:
    if balance <= 0 or price <= 0:
        return 0.0
    if not 0 < max_position_pct <= 1:
        raise ValueError("max_position_pct must be between 0 and 1")
    return (balance * max_position_pct) / price


def approve_order(balance: float, price: float, max_position_pct: float) -> RiskDecision:
    quantity = calculate_position_size(balance, price, max_position_pct)
    if quantity <= 0:
        return RiskDecision(False, 0.0, "invalid balance or price")
    return RiskDecision(True, quantity, "within configured position limit")


@dataclass(frozen=True)
class RiskLimits:
    max_position_pct: float = 0.02
    max_total_exposure_pct: float = 0.20
    max_daily_loss_pct: float = 0.02
    max_entries_per_token: int = 2

    def validate(self) -> None:
        if not 0 < self.max_position_pct <= 1:
            raise ValueError("max_position_pct must be between 0 and 1")
        if not 0 < self.max_total_exposure_pct <= 1:
            raise ValueError("max_total_exposure_pct must be between 0 and 1")
        if not 0 < self.max_daily_loss_pct < 1:
            raise ValueError("max_daily_loss_pct must be between 0 and 1")
        if self.max_total_exposure_pct < self.max_position_pct:
            raise ValueError("max_total_exposure_pct must be >= max_position_pct")
        if self.max_entries_per_token <= 0:
            raise ValueError("max_entries_per_token must be positive")


class RiskManager:
    """Deterministic pre-trade risk gate. It does not choose trades."""

    def __init__(self, limits: RiskLimits):
        limits.validate()
        self.limits = limits

    def daily_loss_breached(self, starting_day_equity: float, current_equity: float) -> bool:
        if starting_day_equity <= 0 or current_equity < 0:
            return True
        loss = (starting_day_equity - current_equity) / starting_day_equity
        return loss > self.limits.max_daily_loss_pct or isclose(
            loss, self.limits.max_daily_loss_pct, rel_tol=1e-12, abs_tol=1e-12
        )

    def approve_entry(
        self,
        *,
        account_equity: float,
        order_price: float,
        current_total_exposure: float,
        current_token_exposure: float,
        token_entries: int,
        starting_day_equity: float,
        current_equity: float,
    ) -> RiskDecision:
        if account_equity <= 0 or order_price <= 0:
            return RiskDecision(False, 0.0, "invalid account equity or price")
        if self.daily_loss_breached(starting_day_equity, current_equity):
            return RiskDecision(False, 0.0, "daily loss limit reached")
        if token_entries >= self.limits.max_entries_per_token:
            return RiskDecision(False, 0.0, "maximum entries per token reached")

        max_token_value = account_equity * self.limits.max_position_pct
        remaining_token_value = max_token_value - max(current_token_exposure, 0.0)
        if remaining_token_value <= 0:
            return RiskDecision(False, 0.0, "maximum token position reached")

        max_total_value = account_equity * self.limits.max_total_exposure_pct
        remaining_total_value = max_total_value - max(current_total_exposure, 0.0)
        if remaining_total_value <= 0:
            return RiskDecision(False, 0.0, "maximum portfolio exposure reached")

        allowed_value = min(remaining_token_value, remaining_total_value)
        quantity = allowed_value / order_price
        return RiskDecision(True, quantity, "entry approved by risk limits")
