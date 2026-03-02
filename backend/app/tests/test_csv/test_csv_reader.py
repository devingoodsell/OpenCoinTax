"""Tests for CSV reader — format detection, parsing of all formats."""

from pathlib import Path

from app.services.csv.csv_reader import parse_csv
from app.services.csv_presets import detect_preset

FIXTURES = Path(__file__).parent.parent / "fixtures"


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
