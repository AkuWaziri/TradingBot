from dataclasses import dataclass


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
