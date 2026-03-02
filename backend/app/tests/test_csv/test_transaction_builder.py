"""Tests for transaction builder — import parsed rows into database."""

from pathlib import Path

from app.services.csv.csv_reader import parse_csv
from app.services.csv.transaction_builder import import_parsed_rows
from app.services.dedup import check_duplicates
from app.models import Transaction, Asset

FIXTURES = Path(__file__).parent.parent / "fixtures"


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
