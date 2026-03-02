"""Tests for CSV validator — utility functions for parsing and validation."""

from app.services.csv.csv_validator import _safe_decimal, _parse_date


class TestSafeDecimal:
    def test_valid(self):
        assert _safe_decimal("123.45") == "123.45"
        assert _safe_decimal("1,234.56") == "1234.56"

    def test_invalid(self):
        assert _safe_decimal("abc") is None
        assert _safe_decimal("") is None
        assert _safe_decimal(None) is None


class TestParseDate:
    def test_iso(self):
        dt = _parse_date("2025-01-15T12:00:00Z")
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 1

    def test_with_format(self):
        dt = _parse_date("2025-01-15 12:00:00 UTC", "%Y-%m-%d %H:%M:%S %Z")
        assert dt is not None

    def test_invalid(self):
        assert _parse_date("not a date") is None
