from risk import approve_order, calculate_position_size


def test_position_size_respects_limit():
    assert calculate_position_size(10_000, 100, 0.10) == 10


def test_order_approved_when_valid():
    decision = approve_order(10_000, 100, 0.10)
    assert decision.approved is True
    assert decision.quantity == 10


def test_invalid_price_rejected():
    decision = approve_order(10_000, 0, 0.10)
    assert decision.approved is False
    assert decision.quantity == 0
