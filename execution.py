from dataclasses import dataclass


@dataclass
class Position:
    quantity: float = 0.0
    average_price: float = 0.0


@dataclass
class PaperAccount:
    cash: float
    position: Position = None

    def __post_init__(self):
        if self.position is None:
            self.position = Position()

    def buy(self, quantity: float, price: float) -> None:
        if quantity <= 0 or price <= 0:
            raise ValueError("quantity and price must be positive")
        cost = quantity * price
        if cost > self.cash:
            raise ValueError("insufficient cash")
        total_quantity = self.position.quantity + quantity
        self.position.average_price = (
            (self.position.quantity * self.position.average_price) + cost
        ) / total_quantity
        self.position.quantity = total_quantity
        self.cash -= cost

    def sell(self, quantity: float, price: float) -> None:
        if quantity <= 0 or price <= 0:
            raise ValueError("quantity and price must be positive")
        if quantity > self.position.quantity:
            raise ValueError("insufficient position")
        self.position.quantity -= quantity
        self.cash += quantity * price
        if self.position.quantity == 0:
            self.position.average_price = 0.0

    def equity(self, market_price: float) -> float:
        if market_price <= 0:
            raise ValueError("market_price must be positive")
        return self.cash + self.position.quantity * market_price
