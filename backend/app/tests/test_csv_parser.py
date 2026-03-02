"""Tests for CSV parsing — format detection, row parsing, and import."""

import pytest
from pathlib import Path
from decimal import Decimal

from app.services.csv_parser import parse_csv, import_parsed_rows, _safe_decimal, _parse_date
from app.services.csv_presets import detect_preset, PRESETS
from app.services.dedup import check_duplicates
from app.models import Transaction, Asset

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------

class TestFormatDetection:
    def test_detect_koinly(self):
        headers = ["Date", "Sent Amount", "Sent Currency", "Received Amount",
                    "Received Currency", "Fee Amount", "Fee Currency",
                    "Net Worth Amount", "Net Worth Currency", "Label",
                    "Description", "TxHash"]
        name, preset = detect_preset(headers)
        assert name == "koinly_universal"

    def test_detect_coinbase(self):
        headers = ["Timestamp", "Transaction Type", "Asset", "Quantity Transacted",
                    "Spot Price Currency", "Spot Price at Transaction", "Subtotal",
                    "Total (inclusive of fees and/or spread)",
                    "Fees and/or Spread", "Notes"]
        name, preset = detect_preset(headers)
        assert name == "coinbase"

    def test_detect_river(self):
        headers = ["Date", "Type", "Amount (BTC)", "Amount (USD)",
                    "Description", "Transaction ID"]
        name, preset = detect_preset(headers)
        assert name == "river"

    def test_unknown_headers(self):
        headers = ["Foo", "Bar", "Baz"]
        name, _ = detect_preset(headers)
        assert name == "unknown"


# ---------------------------------------------------------------------------
# Koinly CSV parsing
# ---------------------------------------------------------------------------

class TestKoinlyParsing:
    def test_parse_koinly_csv(self):
        content = (FIXTURES / "koinly_sample.csv").read_text()
        result = parse_csv(content, "koinly_universal")

        assert result.detected_format == "koinly_universal"
        assert result.total_rows == 4
        assert result.valid_rows >= 3

    def test_koinly_buy(self):
        content = (FIXTURES / "koinly_sample.csv").read_text()
        result = parse_csv(content, "koinly_universal")
        buy_row = result.rows[0]

        assert buy_row.from_amount == "30000.00"
        assert buy_row.from_asset == "USD"
        assert buy_row.to_amount == "1.0"
        assert buy_row.to_asset == "BTC"
        assert buy_row.fee_amount == "5.00"
        assert buy_row.tx_hash == "abc123"

    def test_koinly_staking_reward(self):
        content = (FIXTURES / "koinly_sample.csv").read_text()
        result = parse_csv(content, "koinly_universal")
        staking_row = result.rows[1]

        assert staking_row.tx_type == "staking_reward"
        assert staking_row.to_amount == "0.01"
        assert staking_row.to_asset == "ETH"

    def test_koinly_trade(self):
        content = (FIXTURES / "koinly_sample.csv").read_text()
        result = parse_csv(content, "koinly_universal")
        trade_row = result.rows[3]

        assert trade_row.from_amount == "1.0"
        assert trade_row.from_asset == "ETH"
        assert trade_row.to_amount == "0.05"
        assert trade_row.to_asset == "BTC"


# ---------------------------------------------------------------------------
# Coinbase CSV parsing
# ---------------------------------------------------------------------------

class TestCoinbaseParsing:
    def test_parse_coinbase_csv(self):
        content = (FIXTURES / "coinbase_sample.csv").read_text()
        result = parse_csv(content, "coinbase")

        assert result.detected_format == "coinbase"
        assert result.total_rows == 4

    def test_coinbase_buy(self):
        content = (FIXTURES / "coinbase_sample.csv").read_text()
        result = parse_csv(content, "coinbase")
        buy_row = result.rows[0]

        assert buy_row.tx_type == "buy"
        assert buy_row.to_amount == "0.5"
        assert buy_row.to_asset == "BTC"

    def test_coinbase_staking_income(self):
        content = (FIXTURES / "coinbase_sample.csv").read_text()
        result = parse_csv(content, "coinbase")
        staking_row = result.rows[2]

        assert staking_row.tx_type == "staking_reward"

    def test_coinbase_convert(self):
        content = (FIXTURES / "coinbase_sample.csv").read_text()
        result = parse_csv(content, "coinbase")
        convert_row = result.rows[3]

        assert convert_row.tx_type == "trade"


# ---------------------------------------------------------------------------
# River CSV parsing
# ---------------------------------------------------------------------------

class TestRiverParsing:
    def test_parse_river_csv(self):
        content = (FIXTURES / "river_sample.csv").read_text()
        result = parse_csv(content, "river")

        assert result.detected_format == "river"
        assert result.total_rows == 4

    def test_river_purchase(self):
        content = (FIXTURES / "river_sample.csv").read_text()
        result = parse_csv(content, "river")
        buy_row = result.rows[0]

        assert buy_row.tx_type == "buy"
        assert buy_row.to_amount == "0.1"


# ---------------------------------------------------------------------------
# Import into database
# ---------------------------------------------------------------------------

class TestImportParsedRows:
    def test_import_creates_transactions(self, db, seed_wallets, seed_assets):
        content = (FIXTURES / "koinly_sample.csv").read_text()
        result = parse_csv(content, "koinly_universal")

        imported, skipped, errors = import_parsed_rows(
            db, result.rows, seed_wallets["Coinbase"].id
        )

        assert imported >= 3
        txns = db.query(Transaction).all()
        assert len(txns) == imported

    def test_import_creates_unknown_assets(self, db, seed_wallets, seed_assets):
        csv_content = (
            "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,"
            "Fee Amount,Fee Currency,Net Worth Amount,Net Worth Currency,"
            "Label,Description,TxHash\n"
            "2025-01-01 12:00:00 UTC,,,100,NEWTOKEN,,,10.00,USD,,Got new token,\n"
        )
        result = parse_csv(csv_content, "koinly_universal")
        import_parsed_rows(db, result.rows, seed_wallets["Coinbase"].id)

        asset = db.query(Asset).filter_by(symbol="NEWTOKEN").first()
        assert asset is not None


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    def test_exact_koinly_id_match(self, db, seed_wallets, seed_assets):
        # Import once
        content = (FIXTURES / "koinly_sample.csv").read_text()
        result = parse_csv(content, "koinly_universal")
        import_parsed_rows(db, result.rows, seed_wallets["Coinbase"].id)

        # Parse again and check for dupes
        result2 = parse_csv(content, "koinly_universal")
        # Set koinly_tx_ids to match tx_hashes (since our CSV uses TxHash)
        for row in result2.rows:
            row.koinly_tx_id = row.tx_hash

        new_rows, matches = check_duplicates(db, result2.rows, seed_wallets["Coinbase"].id)

        # All rows with tx_hashes should be detected as dupes
        assert len(matches) > 0

    def test_no_false_positives(self, db, seed_wallets, seed_assets):
        # Empty DB — nothing should match
        content = (FIXTURES / "koinly_sample.csv").read_text()
        result = parse_csv(content, "koinly_universal")

        new_rows, matches = check_duplicates(db, result.rows, seed_wallets["Coinbase"].id)

        assert len(matches) == 0
        assert len(new_rows) == len(result.rows)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

class TestUtilities:
    def test_safe_decimal_valid(self):
        assert _safe_decimal("123.45") == "123.45"
        assert _safe_decimal("1,234.56") == "1234.56"

    def test_safe_decimal_invalid(self):
        assert _safe_decimal("abc") is None
        assert _safe_decimal("") is None
        assert _safe_decimal(None) is None

    def test_parse_date_iso(self):
        dt = _parse_date("2025-01-15T12:00:00Z")
        assert dt is not None
        assert dt.year == 2025
        assert dt.month == 1

    def test_parse_date_with_format(self):
        dt = _parse_date("2025-01-15 12:00:00 UTC", "%Y-%m-%d %H:%M:%S %Z")
        assert dt is not None

    def test_parse_date_invalid(self):
        assert _parse_date("not a date") is None
