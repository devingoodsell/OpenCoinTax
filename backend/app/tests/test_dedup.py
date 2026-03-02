"""Tests for dedup — duplicate transaction detection."""

from datetime import datetime, timezone, timedelta

from app.services.dedup import check_duplicates, DedupMatch
from app.services.csv import ParsedRow
from app.tests.factories import create_asset, create_wallet, create_transaction


class TestCheckDuplicates:
    def test_exact_koinly_id_match(self, db):
        wallet = create_wallet(db, name="Coinbase")
        btc = create_asset(db, symbol="BTC")
        db.commit()

        # Existing transaction with koinly_tx_id
        create_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=btc.id,
            to_amount="1.0",
        )
        db.execute(
            __import__("sqlalchemy").text(
                "UPDATE transactions SET koinly_tx_id = 'K-12345' WHERE id = 1"
            )
        )
        db.commit()

        row = ParsedRow(row_number=1, koinly_tx_id="K-12345",
                        datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
                        to_amount="1.0")
        new_rows, matches = check_duplicates(db, [row], wallet.id)

        assert len(matches) == 1
        assert matches[0].match_type == "exact_koinly_id"
        assert len(new_rows) == 0

    def test_exact_tx_hash_match(self, db):
        wallet = create_wallet(db, name="Ledger")
        btc = create_asset(db, symbol="BTC")
        db.commit()

        dt = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        create_transaction(
            db,
            datetime_utc=dt,
            tx_type="deposit",
            to_wallet_id=wallet.id,
            to_asset_id=btc.id,
            to_amount="0.5",
            tx_hash="0xabc123",
        )
        db.commit()

        row = ParsedRow(row_number=1, tx_hash="0xabc123",
                        datetime_utc=dt, to_amount="0.5")
        new_rows, matches = check_duplicates(db, [row], wallet.id)

        assert len(matches) == 1
        assert matches[0].match_type == "exact_tx_hash"

    def test_fuzzy_match(self, db):
        wallet = create_wallet(db, name="Coinbase")
        btc = create_asset(db, symbol="BTC")
        db.commit()

        dt = datetime(2025, 2, 1, 10, 0, 0, tzinfo=timezone.utc)
        create_transaction(
            db,
            datetime_utc=dt,
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=btc.id,
            to_amount="1.5",
        )
        db.commit()

        # Same amounts, within 60s window
        row = ParsedRow(
            row_number=1,
            datetime_utc=dt + timedelta(seconds=30),
            to_amount="1.5",
        )
        new_rows, matches = check_duplicates(db, [row], wallet.id)

        assert len(matches) == 1
        assert matches[0].match_type == "fuzzy"

    def test_no_duplicate(self, db):
        wallet = create_wallet(db, name="River")
        create_asset(db, symbol="BTC")
        db.commit()

        row = ParsedRow(
            row_number=1,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            to_amount="0.1",
        )
        new_rows, matches = check_duplicates(db, [row], wallet.id)

        assert len(matches) == 0
        assert len(new_rows) == 1

    def test_error_rows_pass_through(self, db):
        wallet = create_wallet(db, name="Coinbase")
        db.commit()

        row = ParsedRow(row_number=1, status="error", error_message="Bad date")
        new_rows, matches = check_duplicates(db, [row], wallet.id)

        assert len(new_rows) == 1
        assert len(matches) == 0
