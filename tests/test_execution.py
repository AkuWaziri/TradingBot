import pytest

from execution import PaperAccount


def test_paper_buy_and_sell():
    account = PaperAccount(1_000)
    account.buy(2, 100)
    assert account.cash == 800
    assert account.position.quantity == 2
    assert account.equity(110) == 1_020

    account.sell(1, 120)
    assert account.cash == 920
    assert account.position.quantity == 1
    assert account.equity(120) == 1_040


def test_cannot_buy_without_cash():
    account = PaperAccount(100)
    with pytest.raises(ValueError):
        account.buy(2, 100)


def test_cannot_sell_without_position():
    account = PaperAccount(100)
    with pytest.raises(ValueError):
        account.sell(1, 100)
