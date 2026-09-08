from risk import RiskLimits, RiskManager, approve_order, calculate_position_size


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


def make_manager():
    return RiskManager(
        RiskLimits(
            max_position_pct=0.02,
            max_total_exposure_pct=0.20,
            max_daily_loss_pct=0.02,
            max_entries_per_token=2,
        )
    )


def test_first_entry_uses_two_percent_token_limit():
    decision = make_manager().approve_entry(
        account_equity=10,
        order_price=1,
        current_total_exposure=0,
        current_token_exposure=0,
        token_entries=0,
        starting_day_equity=10,
        current_equity=10,
    )
    assert decision.approved is True
    assert decision.quantity == 0.2


def test_second_entry_only_uses_remaining_token_capacity():
    decision = make_manager().approve_entry(
        account_equity=10,
        order_price=1,
        current_total_exposure=0.1,
        current_token_exposure=0.1,
        token_entries=1,
        starting_day_equity=10,
        current_equity=10,
    )
    assert decision.approved is True
    assert decision.quantity == 0.1


def test_third_entry_is_rejected():
    decision = make_manager().approve_entry(
        account_equity=10,
        order_price=1,
        current_total_exposure=0.2,
        current_token_exposure=0.2,
        token_entries=2,
        starting_day_equity=10,
        current_equity=10,
    )
    assert decision.approved is False
    assert decision.quantity == 0
    assert "maximum entries" in decision.reason


def test_daily_loss_limit_blocks_new_entries():
    decision = make_manager().approve_entry(
        account_equity=10,
        order_price=1,
        current_total_exposure=0,
        current_token_exposure=0,
        token_entries=0,
        starting_day_equity=10,
        current_equity=9.8,
    )
    assert decision.approved is False
    assert "daily loss" in decision.reason


def test_total_exposure_limit_caps_new_entry():
    decision = make_manager().approve_entry(
        account_equity=10,
        order_price=1,
        current_total_exposure=1.99,
        current_token_exposure=0,
        token_entries=0,
        starting_day_equity=10,
        current_equity=10,
    )
    assert decision.approved is True
    assert decision.quantity == 0.01
