"""Integration tests for the import API endpoints.

Tests POST /api/import/csv, POST /api/import/csv/confirm, GET /api/import/logs.
"""

from datetime import datetime
from decimal import Decimal
from io import BytesIO

import pytest

from app.models import Transaction, ImportLog
from app.tests.conftest import make_transaction


KOINLY_CSV = """Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Net Worth Amount,Net Worth Currency,Label,Description,TxHash
2025-01-15 10:00:00 UTC,,USD,1.0,BTC,,,,USD,,Bought BTC,abc123
2025-06-15 14:00:00 UTC,0.5,BTC,,USD,,,,USD,,Sold BTC,def456
"""

SIMPLE_CSV = """Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Net Worth Amount,Net Worth Currency,Label,Description,TxHash
2025-02-01 12:00:00 UTC,,USD,2.0,ETH,,,,USD,,Bought ETH,tx001
"""


class TestCsvUpload:

    def test_upload_koinly_csv(self, client, db, seed_assets, seed_wallets, seed_settings):
        """POST /api/import/csv parses a Koinly CSV and returns preview."""
        resp = client.post(
            "/api/import/csv",
            files={"file": ("test.csv", BytesIO(KOINLY_CSV.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "koinly" in data["detected_format"]
        assert data["total_rows"] == 2
        assert data["valid_rows"] >= 1
        assert len(data["rows"]) == 2

    def test_upload_empty_file(self, client, db, seed_assets, seed_wallets, seed_settings):
        """Uploading an empty file returns 0 rows."""
        empty = "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Net Worth Amount,Net Worth Currency,Label,Description,TxHash\n"
        resp = client.post(
            "/api/import/csv",
            files={"file": ("empty.csv", BytesIO(empty.encode()), "text/csv")},
        )
        assert resp.status_code == 200
        assert resp.json()["total_rows"] == 0

    def test_upload_no_file(self, client, db, seed_assets, seed_wallets, seed_settings):
        """POST /api/import/csv without a file returns 422."""
        resp = client.post("/api/import/csv")
        assert resp.status_code == 422


class TestCsvConfirm:

    def test_confirm_import(self, client, db, seed_assets, seed_wallets, seed_settings):
        """Upload then confirm imports transactions into the database."""
        wallet = seed_wallets["Coinbase"]

        # Step 1: Upload
        upload_resp = client.post(
            "/api/import/csv",
            files={"file": ("test.csv", BytesIO(KOINLY_CSV.encode()), "text/csv")},
        )
        assert upload_resp.status_code == 200
        rows = upload_resp.json()["rows"]
        row_numbers = [r["row_number"] for r in rows if r["status"] != "error"]

        # Step 2: Confirm
        confirm_resp = client.post(
            "/api/import/csv/confirm",
            json={"wallet_id": wallet.id, "rows": row_numbers},
        )
        assert confirm_resp.status_code == 200
        data = confirm_resp.json()
        assert data["transactions_imported"] >= 1
        assert data["import_log_id"] is not None

        # Verify transactions exist
        txns = db.query(Transaction).filter(Transaction.source == "csv_import").all()
        assert len(txns) >= 1

    def test_confirm_no_pending_parse(self, client, db, seed_assets, seed_wallets, seed_settings):
        """Confirming without a prior upload returns 404."""
        wallet = seed_wallets["Coinbase"]

        resp = client.post(
            "/api/import/csv/confirm",
            json={"wallet_id": wallet.id, "rows": [1, 2]},
        )
        assert resp.status_code == 404

    def test_dedup_skips_duplicates(self, client, db, seed_assets, seed_wallets, seed_settings):
        """Importing the same CSV twice skips duplicates on the second run."""
        wallet = seed_wallets["Coinbase"]

        # First import
        upload1 = client.post(
            "/api/import/csv",
            files={"file": ("test.csv", BytesIO(SIMPLE_CSV.encode()), "text/csv")},
        )
        rows1 = upload1.json()["rows"]
        row_nums = [r["row_number"] for r in rows1 if r["status"] != "error"]

        confirm1 = client.post(
            "/api/import/csv/confirm",
            json={"wallet_id": wallet.id, "rows": row_nums},
        )
        first_imported = confirm1.json()["transactions_imported"]
        assert first_imported >= 1

        # Second import — same data
        upload2 = client.post(
            "/api/import/csv",
            files={"file": ("test.csv", BytesIO(SIMPLE_CSV.encode()), "text/csv")},
        )
        rows2 = upload2.json()["rows"]
        row_nums2 = [r["row_number"] for r in rows2 if r["status"] != "error"]

        confirm2 = client.post(
            "/api/import/csv/confirm",
            json={"wallet_id": wallet.id, "rows": row_nums2},
        )
        data2 = confirm2.json()
        # Second import should skip all (or most) as duplicates
        assert data2["transactions_skipped"] >= first_imported


# ---------------------------------------------------------------------------
# Coinbase CSV — dedup tests
# ---------------------------------------------------------------------------

# Minimal Coinbase-format CSV (with metadata header)
COINBASE_CSV = """\

Transactions
User,"Test User",abc123
ID,Timestamp,Transaction Type,Asset,Quantity Transacted,Price Currency,Price at Transaction,Subtotal,Total (inclusive of fees and/or spread),Fees and/or Spread,Notes
cb_id_001,2025-01-10 12:00:00 UTC,Buy,BTC,0.5,USD,$40000.00,$20000.00,$20050.00,$50.00,Bought 0.5 BTC
cb_id_002,2025-02-15 09:00:00 UTC,Staking Income,ETH,0.01,USD,$3000.00,$30.00,$30.00,$0.00,Staking reward
"""


def _import_coinbase(client, csv_content: str, wallet_id: int) -> dict:
    """Upload + confirm a Coinbase CSV. Returns confirm response JSON."""
    upload = client.post(
        "/api/import/csv",
        files={"file": ("coinbase.csv", BytesIO(csv_content.encode()), "text/csv")},
    )
    assert upload.status_code == 200
    rows = upload.json()["rows"]
    row_nums = [r["row_number"] for r in rows if r["status"] == "valid"]
    confirm = client.post(
        "/api/import/csv/confirm",
        json={"wallet_id": wallet_id, "rows": row_nums},
    )
    assert confirm.status_code == 200
    return confirm.json()


class TestCoinbaseDedup:
    """Coinbase imports should not create duplicates."""

    def test_preview_flags_duplicates(self, client, db, seed_assets, seed_wallets, seed_settings):
        """Second upload of same Coinbase CSV flags rows as duplicate in preview."""
        wallet = seed_wallets["Coinbase"]

        # First import
        _import_coinbase(client, COINBASE_CSV, wallet.id)

        # Second upload (preview only, no confirm)
        upload2 = client.post(
            "/api/import/csv",
            files={"file": ("coinbase.csv", BytesIO(COINBASE_CSV.encode()), "text/csv")},
        )
        assert upload2.status_code == 200
        data = upload2.json()

        # Both rows should now be flagged as duplicates (warnings)
        dup_rows = [r for r in data["rows"] if "duplicate" in (r.get("error_message") or "").lower()]
        valid_rows = [r for r in data["rows"] if r["status"] == "valid"]
        assert len(dup_rows) == 2
        assert len(valid_rows) == 0
        assert data["valid_rows"] == 0
        assert data["warning_rows"] >= 2

    def test_confirm_skips_duplicates(self, client, db, seed_assets, seed_wallets, seed_settings):
        """Confirming a second Coinbase import skips duplicate rows."""
        wallet = seed_wallets["Coinbase"]

        # First import
        data1 = _import_coinbase(client, COINBASE_CSV, wallet.id)
        assert data1["transactions_imported"] == 2

        # Count transactions before second import
        tx_count_before = db.query(Transaction).count()

        # Second import — same CSV
        data2 = _import_coinbase(client, COINBASE_CSV, wallet.id)

        # Should skip all as duplicates, import 0
        assert data2["transactions_imported"] == 0
        assert data2["transactions_skipped"] >= 2

        # No new transactions created
        tx_count_after = db.query(Transaction).count()
        assert tx_count_after == tx_count_before

    def test_first_import_has_no_false_duplicates(self, client, db, seed_assets, seed_wallets, seed_settings):
        """First Coinbase import should show all rows as valid (no false positives)."""
        upload = client.post(
            "/api/import/csv",
            files={"file": ("coinbase.csv", BytesIO(COINBASE_CSV.encode()), "text/csv")},
        )
        assert upload.status_code == 200
        data = upload.json()
        assert data["detected_format"] == "coinbase"
        assert data["valid_rows"] == 2
        valid = [r for r in data["rows"] if r["status"] == "valid"]
        assert len(valid) == 2

    def test_partial_duplicates(self, client, db, seed_assets, seed_wallets, seed_settings):
        """If only some rows are duplicates, only those are flagged."""
        wallet = seed_wallets["Coinbase"]

        # Import the first CSV
        _import_coinbase(client, COINBASE_CSV, wallet.id)

        # Upload a CSV that contains one old row and one new row
        mixed_csv = """\

Transactions
User,"Test User",abc123
ID,Timestamp,Transaction Type,Asset,Quantity Transacted,Price Currency,Price at Transaction,Subtotal,Total (inclusive of fees and/or spread),Fees and/or Spread,Notes
cb_id_001,2025-01-10 12:00:00 UTC,Buy,BTC,0.5,USD,$40000.00,$20000.00,$20050.00,$50.00,Bought 0.5 BTC
cb_id_new,2025-03-01 15:00:00 UTC,Buy,ETH,1.0,USD,$3500.00,$3500.00,$3525.00,$25.00,Bought 1.0 ETH
"""
        upload = client.post(
            "/api/import/csv",
            files={"file": ("mixed.csv", BytesIO(mixed_csv.encode()), "text/csv")},
        )
        data = upload.json()
        assert data["valid_rows"] == 1  # only the new row
        assert data["warning_rows"] >= 1  # the duplicate

        dup_rows = [r for r in data["rows"] if "duplicate" in (r.get("error_message") or "").lower()]
        valid_rows = [r for r in data["rows"] if r["status"] == "valid"]
        assert len(dup_rows) == 1
        assert dup_rows[0]["tx_hash"] == "cb_id_001"
        assert len(valid_rows) == 1
        assert valid_rows[0]["tx_hash"] == "cb_id_new"


class TestCrossSourceDedup:
    """Dedup should detect duplicates even when imported from different sources."""

    def test_koinly_imported_detected_by_coinbase_upload(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """Transactions imported via Koinly (different tx_hash) are flagged as
        duplicates when the same data is uploaded in Coinbase CSV format.

        Uses fuzzy matching: datetime within 60s + same amounts.
        """
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        # Simulate a Koinly-imported transaction (different tx_hash)
        make_transaction(
            db,
            datetime_utc=datetime(2025, 1, 10, 12, 0, 0),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_amount="0.5",
            to_asset_id=btc.id,
            to_value_usd="20000.00",
            tx_hash="koinly_abc123",  # Different hash than Coinbase ID
            source="koinly_import",
        )

        # Now upload a Coinbase CSV with the same transaction
        upload = client.post(
            "/api/import/csv",
            files={"file": ("coinbase.csv", BytesIO(COINBASE_CSV.encode()), "text/csv")},
        )
        assert upload.status_code == 200
        data = upload.json()

        # The BTC buy row (cb_id_001) should be flagged as duplicate via fuzzy match
        dup_rows = [
            r for r in data["rows"]
            if "duplicate" in (r.get("error_message") or "").lower()
        ]
        # At minimum the BTC buy should be detected
        btc_buy_rows = [
            r for r in data["rows"]
            if r.get("to_amount") == "0.5" and r.get("to_asset") == "BTC"
        ]
        assert len(btc_buy_rows) == 1
        assert btc_buy_rows[0]["status"] == "warning"
        assert "duplicate" in btc_buy_rows[0]["error_message"].lower()

    def test_withdrawal_matches_transfer_approx_amount(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """A Coinbase withdrawal (0.50000588 BTC) should match an existing
        transfer (0.5 BTC) that was created when the withdrawal was paired
        with a deposit during Koinly import.

        Uses approximate matching (within 1%) to handle fee differences,
        a 60-minute time window to handle Coinbase send-initiation vs
        blockchain confirmation time differences (~48 min apart here for BTC),
        and asset matching to prevent false positives.
        """
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        # Simulate existing transfer (from Koinly import) — exact 0.5 BTC
        # Blockchain confirmed at 17:09:42 (48 min after Coinbase initiation)
        make_transaction(
            db,
            datetime_utc=datetime(2025, 9, 27, 17, 9, 42),
            tx_type="transfer",
            from_wallet_id=wallet.id,
            from_amount="0.5",
            from_asset_id=btc.id,
            to_wallet_id=wallet.id,
            to_amount="0.5",
            to_asset_id=btc.id,
            tx_hash="koinly_transfer_hash",
            source="koinly_import",
        )

        # Upload Coinbase CSV with Send at 16:21:37 (initiation time, ~48 min before confirm)
        withdrawal_csv = """\

Transactions
User,"Test User",abc123
ID,Timestamp,Transaction Type,Asset,Quantity Transacted,Price Currency,Price at Transaction,Subtotal,Total (inclusive of fees and/or spread),Fees and/or Spread,Notes
cb_withdraw_001,2025-09-27 16:21:37 UTC,Send,BTC,0.50000588,USD,$109449.99,$54725.64,$54725.64,$0.00,Sent 0.5 BTC
"""
        upload = client.post(
            "/api/import/csv",
            files={"file": ("coinbase.csv", BytesIO(withdrawal_csv.encode()), "text/csv")},
        )
        assert upload.status_code == 200
        data = upload.json()

        # The withdrawal should be flagged as duplicate (approx amount + 60min window + same asset)
        rows = data["rows"]
        assert len(rows) == 1
        assert rows[0]["status"] == "warning"
        assert "duplicate" in rows[0]["error_message"].lower()

    def test_fuzzy_dedup_no_false_positives(
        self, client, db, seed_assets, seed_wallets, seed_settings
    ):
        """Fuzzy dedup should not flag transactions with different amounts as duplicates."""
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        # Create a BTC buy with different amount at similar time
        make_transaction(
            db,
            datetime_utc=datetime(2025, 1, 10, 12, 0, 0),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_amount="1.0",  # Different amount than Coinbase CSV (0.5)
            to_asset_id=btc.id,
            to_value_usd="40000.00",
            tx_hash="other_hash",
            source="koinly_import",
        )

        upload = client.post(
            "/api/import/csv",
            files={"file": ("coinbase.csv", BytesIO(COINBASE_CSV.encode()), "text/csv")},
        )
        assert upload.status_code == 200
        data = upload.json()

        # The BTC buy (0.5) should NOT be flagged — amounts don't match (0.5 vs 1.0)
        btc_buy_rows = [
            r for r in data["rows"]
            if r.get("to_amount") == "0.5" and r.get("to_asset") == "BTC"
        ]
        assert len(btc_buy_rows) == 1
        assert btc_buy_rows[0]["status"] == "valid"


class TestImportLogs:

    def test_logs_after_import(self, client, db, seed_assets, seed_wallets, seed_settings):
        """GET /api/import/logs shows import history."""
        wallet = seed_wallets["Coinbase"]

        # Do an import first
        upload_resp = client.post(
            "/api/import/csv",
            files={"file": ("test.csv", BytesIO(SIMPLE_CSV.encode()), "text/csv")},
        )
        rows = upload_resp.json()["rows"]
        row_nums = [r["row_number"] for r in rows if r["status"] != "error"]
        client.post(
            "/api/import/csv/confirm",
            json={"wallet_id": wallet.id, "rows": row_nums},
        )

        resp = client.get("/api/import/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        log = data["items"][0]
        assert log["status"] == "completed"
        assert log["transactions_imported"] >= 1

    def test_logs_empty(self, client, db, seed_assets, seed_wallets, seed_settings):
        """No imports → empty log list."""
        resp = client.get("/api/import/logs")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_logs_pagination(self, client, db, seed_assets, seed_wallets, seed_settings):
        """Pagination parameters are respected."""
        resp = client.get("/api/import/logs?page=1&page_size=5")
        assert resp.status_code == 200
