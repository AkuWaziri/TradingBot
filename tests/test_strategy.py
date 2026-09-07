import pytest

from strategy import generate_signal, moving_average


def test_moving_average():
    assert moving_average([1, 2, 3, 4], 2) == 3.5


def test_buy_signal():
    assert generate_signal([1, 1, 1, 2, 3], 2, 5).action == "BUY"


def test_sell_signal():
    assert generate_signal([5, 5, 5, 4, 3], 2, 5).action == "SELL"


def test_hold_when_not_enough_data():
    assert generate_signal([1, 2, 3], 2, 5).action == "HOLD"


def test_invalid_windows():
    with pytest.raises(ValueError):
        generate_signal([1, 2, 3], 5, 2)
