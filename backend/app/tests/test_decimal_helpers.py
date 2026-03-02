from decimal import Decimal

from app.utils.decimal_helpers import PENNY, ZERO, quantize_usd, to_decimal


class TestToDecimal:
    def test_string_conversion(self):
        assert to_decimal("123.456789") == Decimal("123.456789")

    def test_none_returns_zero(self):
        assert to_decimal(None) is ZERO

    def test_empty_string_returns_zero(self):
        assert to_decimal("") is ZERO

    def test_decimal_passthrough(self):
        d = Decimal("42")
        assert to_decimal(d) is d

    def test_int_conversion(self):
        assert to_decimal(100) == Decimal("100")

    def test_float_conversion(self):
        result = to_decimal(1.5)
        assert result == Decimal("1.5")

    def test_negative_string(self):
        assert to_decimal("-50.25") == Decimal("-50.25")

    def test_zero_string(self):
        assert to_decimal("0") == ZERO


class TestConstants:
    def test_zero_value(self):
        assert ZERO == Decimal("0")

    def test_penny_value(self):
        assert PENNY == Decimal("0.01")


class TestQuantizeUsd:
    def test_standard_rounding(self):
        assert quantize_usd(Decimal("123.4567")) == Decimal("123.46")

    def test_round_half_up(self):
        assert quantize_usd(Decimal("10.005")) == Decimal("10.01")

    def test_already_two_decimals(self):
        assert quantize_usd(Decimal("5.50")) == Decimal("5.50")

    def test_whole_number(self):
        assert quantize_usd(Decimal("100")) == Decimal("100.00")

    def test_negative_amount(self):
        assert quantize_usd(Decimal("-99.999")) == Decimal("-100.00")
