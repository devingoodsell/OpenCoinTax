"""Tests for Ledger Live CSV import — parsing, dedup, enrichment."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models import Account, Asset, Transaction
from app.services.csv_parser import (
    ParsedRow,
    import_parsed_rows,
    parse_csv,
    _find_ledger_duplicate,
    _resolve_asset,
    _resolve_ledger_account,
    _update_existing_from_ledger,
)
from app.services.csv_presets import detect_preset
from app.tests.conftest import make_transaction

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Ledger format detection
# ---------------------------------------------------------------------------


class TestLedgerDetection:
    def test_detect_ledger_headers(self):
        headers = [
            "Operation Date", "Status", "Currency Ticker", "Operation Type",
            "Operation Amount", "Operation Fees", "Operation Hash",
            "Account Name", "Account xpub",
        ]
        name, preset = detect_preset(headers)
        assert name == "ledger"

    def test_ledger_before_koinly(self):
        """Ledger detection takes priority even if Koinly headers also present."""
        headers = [
            "Operation Date", "Operation Type",
            "Sent Amount", "Received Amount",  # Koinly headers
        ]
        name, _ = detect_preset(headers)
        assert name == "ledger"


# ---------------------------------------------------------------------------
# Ledger CSV parsing
# ---------------------------------------------------------------------------


class TestLedgerParsing:
    def test_parse_ledger_csv(self):
        content = (FIXTURES / "ledger_sample.csv").read_text()
        result = parse_csv(content)

        assert result.detected_format == "ledger"
        assert result.total_rows == 7

    def test_in_operation_parsed_as_deposit(self):
        content = (FIXTURES / "ledger_sample.csv").read_text()
        result = parse_csv(content)
        # First row: BTC IN 0.5
        row = result.rows[0]

        assert row.status == "valid"
        assert row.tx_type == "deposit"
        assert row.to_amount == "0.5"
        assert row.to_asset == "BTC"
        assert row.from_amount is None
        assert row.to_value_usd is not None

    def test_out_operation_moves_to_from(self):
        content = (FIXTURES / "ledger_sample.csv").read_text()
        result = parse_csv(content)
        # Second row: BTC OUT 0.1
        row = result.rows[1]

        assert row.status == "valid"
        assert row.tx_type == "withdrawal"
        assert row.from_amount == "0.1"
        assert row.from_asset == "BTC"
        assert row.to_amount is None
        assert row.from_value_usd is not None

    def test_out_fee_is_preserved(self):
        content = (FIXTURES / "ledger_sample.csv").read_text()
        result = parse_csv(content)
        row = result.rows[1]  # BTC OUT with fee

        assert row.fee_amount == "0.00001"

    def test_delegate_imported_as_fee(self):
        content = (FIXTURES / "ledger_sample.csv").read_text()
        result = parse_csv(content)
        # Fourth row: SOL DELEGATE
        row = result.rows[3]

        assert row.status == "valid"
        assert row.tx_type == "fee"
        assert row.from_amount == "0.00001"
        assert row.from_asset == "SOL"
        assert row.label == "delegate"

    def test_reward_parsed_as_staking_reward(self):
        content = (FIXTURES / "ledger_sample.csv").read_text()
        result = parse_csv(content)
        # Fifth row: ATOM REWARD
        row = result.rows[4]

        assert row.status == "valid"
        assert row.tx_type == "staking_reward"
        assert row.to_amount == "0.5"
        assert row.to_asset == "ATOM"

    def test_fees_skipped_as_warning(self):
        content = (FIXTURES / "ledger_sample.csv").read_text()
        result = parse_csv(content)
        # Sixth row: ETH FEES
        row = result.rows[5]

        assert row.status == "warning"
        assert "fees" in row.error_message.lower()

    def test_asset_symbols_uppercased(self):
        """stETH in CSV → STETH in parsed row."""
        csv = (
            "Operation Date,Status,Currency Ticker,Operation Type,Operation Amount,"
            "Operation Fees,Operation Hash,Account Name,Account xpub,"
            "Countervalue Ticker,Countervalue at Operation Date,Countervalue at CSV Export\n"
            "2024-01-01T12:00:00.000Z,Confirmed,stETH,IN,1.5,0,hash1,"
            "L1-Ethereum,0xABCD,USD,5000.00,4800.00\n"
        )
        result = parse_csv(csv)
        assert result.rows[0].to_asset == "STETH"

    def test_account_info_in_description(self):
        content = (FIXTURES / "ledger_sample.csv").read_text()
        result = parse_csv(content)
        row = result.rows[0]  # BTC IN

        assert row.description is not None
        assert "Account: L1-Bitcoin" in row.description
        assert "Address: xpub6DLpq2zCmWs7o2nN" in row.description

    def test_date_format_with_milliseconds(self):
        content = (FIXTURES / "ledger_sample.csv").read_text()
        result = parse_csv(content)
        row = result.rows[0]

        assert row.datetime_utc is not None
        assert row.datetime_utc.year == 2024
        assert row.datetime_utc.month == 6
        assert row.datetime_utc.day == 15


# ---------------------------------------------------------------------------
# Ledger dedup — matching by tx_hash + asset + amount
# ---------------------------------------------------------------------------


class TestLedgerDedup:
    def test_single_match_by_hash(self, db, seed_assets, seed_wallets):
        """A Ledger row with matching tx_hash finds the existing transaction."""
        btc = seed_assets["BTC"]
        ledger = seed_wallets["Ledger"]

        make_transaction(
            db,
            datetime_utc=datetime(2024, 6, 15, 10, 30, tzinfo=timezone.utc),
            tx_type="deposit",
            to_wallet_id=ledger.id,
            to_amount="0.5",
            to_asset_id=btc.id,
            to_value_usd="25000",
            tx_hash="abc123hash",
            source="koinly_import",
        )

        row = ParsedRow(
            row_number=2,
            tx_type="deposit",
            to_amount="0.5",
            to_asset="BTC",
            tx_hash="abc123hash",
        )

        match = _find_ledger_duplicate(db, row, None, btc.id)
        assert match is not None
        assert match.tx_hash == "abc123hash"

    def test_case_insensitive_hash(self, db, seed_assets, seed_wallets):
        """tx_hash matching is case-insensitive."""
        btc = seed_assets["BTC"]
        ledger = seed_wallets["Ledger"]

        make_transaction(
            db,
            datetime_utc=datetime(2024, 6, 15, 10, 30, tzinfo=timezone.utc),
            tx_type="deposit",
            to_wallet_id=ledger.id,
            to_amount="0.5",
            to_asset_id=btc.id,
            tx_hash="ABC123HASH",
            source="koinly_import",
        )

        row = ParsedRow(
            row_number=2,
            to_amount="0.5",
            to_asset="BTC",
            tx_hash="abc123hash",
        )

        match = _find_ledger_duplicate(db, row, None, btc.id)
        assert match is not None

    def test_multi_hash_matches_by_asset_amount(self, db, seed_assets, seed_wallets):
        """When multiple txs share a hash (Cosmos multi-claim), match by asset+amount."""
        atom = seed_assets["ATOM"]
        eth = seed_assets["ETH"]
        ledger = seed_wallets["Ledger"]

        # Two transactions with same hash, different assets
        make_transaction(
            db,
            datetime_utc=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            tx_type="staking_reward",
            to_wallet_id=ledger.id,
            to_amount="10.5",
            to_asset_id=atom.id,
            tx_hash="cosmos_multi_hash",
            source="koinly_import",
        )
        make_transaction(
            db,
            datetime_utc=datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            tx_type="staking_reward",
            to_wallet_id=ledger.id,
            to_amount="0.001",
            to_asset_id=eth.id,
            tx_hash="cosmos_multi_hash",
            source="koinly_import",
        )

        # Ledger row for the ATOM reward
        row = ParsedRow(
            row_number=2,
            to_amount="10.5",
            to_asset="ATOM",
            tx_hash="cosmos_multi_hash",
        )

        match = _find_ledger_duplicate(db, row, None, atom.id)
        assert match is not None
        assert match.to_asset_id == atom.id
        assert match.to_amount == "10.5"

    def test_no_match_different_hash(self, db, seed_assets, seed_wallets):
        """Rows with different tx_hash should not match."""
        btc = seed_assets["BTC"]
        ledger = seed_wallets["Ledger"]

        make_transaction(
            db,
            datetime_utc=datetime(2024, 6, 15, 10, 30, tzinfo=timezone.utc),
            tx_type="deposit",
            to_wallet_id=ledger.id,
            to_amount="0.5",
            to_asset_id=btc.id,
            tx_hash="existing_hash",
            source="koinly_import",
        )

        row = ParsedRow(
            row_number=2,
            to_amount="0.5",
            to_asset="BTC",
            tx_hash="different_hash",
        )

        match = _find_ledger_duplicate(db, row, None, btc.id)
        assert match is None

    def test_no_match_without_hash(self, db, seed_assets, seed_wallets):
        """Rows without tx_hash never match."""
        row = ParsedRow(row_number=2, to_amount="0.5", to_asset="BTC", tx_hash=None)
        match = _find_ledger_duplicate(db, row, None, seed_assets["BTC"].id)
        assert match is None


# ---------------------------------------------------------------------------
# Ledger enrichment — updating existing transactions
# ---------------------------------------------------------------------------


class TestLedgerEnrichment:
    def test_updates_fee_info(self, db, seed_assets, seed_wallets):
        """Enrichment adds fee data from Ledger to existing transaction."""
        btc = seed_assets["BTC"]
        ledger = seed_wallets["Ledger"]

        tx = make_transaction(
            db,
            datetime_utc=datetime(2024, 6, 15, 10, 30, tzinfo=timezone.utc),
            tx_type="deposit",
            to_wallet_id=ledger.id,
            to_amount="0.5",
            to_asset_id=btc.id,
            tx_hash="abc123hash",
        )

        row = ParsedRow(
            row_number=2,
            fee_amount="0.00001",
            fee_asset="BTC",
            description="Account: L1-Bitcoin | Address: xpub123",
            raw_data={"Operation Type": "IN"},
        )

        _update_existing_from_ledger(db, tx, row, btc.id, ledger.id)

        assert tx.fee_amount == "0.00001"
        assert tx.fee_asset_id == btc.id

    def test_appends_description(self, db, seed_assets, seed_wallets):
        """Enrichment appends Ledger account info to existing description."""
        btc = seed_assets["BTC"]
        ledger = seed_wallets["Ledger"]

        tx = make_transaction(
            db,
            datetime_utc=datetime(2024, 6, 15, 10, 30, tzinfo=timezone.utc),
            tx_type="deposit",
            to_wallet_id=ledger.id,
            to_amount="0.5",
            to_asset_id=btc.id,
            description="Original description",
        )

        row = ParsedRow(
            row_number=2,
            description="Account: L1-Bitcoin | Address: xpub123",
            raw_data={},
        )

        _update_existing_from_ledger(db, tx, row, None, ledger.id)

        assert "Original description" in tx.description
        assert "Account: L1-Bitcoin" in tx.description

    def test_stores_ledger_raw_data(self, db, seed_assets, seed_wallets):
        """Enrichment stores Ledger raw data alongside existing raw_data."""
        btc = seed_assets["BTC"]
        ledger = seed_wallets["Ledger"]

        tx = make_transaction(
            db,
            datetime_utc=datetime(2024, 6, 15, 10, 30, tzinfo=timezone.utc),
            tx_type="deposit",
            to_wallet_id=ledger.id,
            to_amount="0.5",
            to_asset_id=btc.id,
        )
        tx.raw_data = json.dumps({"koinly_data": "original"})
        db.commit()

        ledger_raw = {"Operation Type": "IN", "Currency Ticker": "BTC"}
        row = ParsedRow(row_number=2, raw_data=ledger_raw)

        _update_existing_from_ledger(db, tx, row, None, ledger.id)

        raw = json.loads(tx.raw_data)
        assert raw["koinly_data"] == "original"
        assert raw["_ledger"]["Operation Type"] == "IN"

    def test_does_not_overwrite_existing_usd_values(self, db, seed_assets, seed_wallets):
        """Enrichment only fills in missing USD values, not overwrite existing ones."""
        btc = seed_assets["BTC"]
        ledger = seed_wallets["Ledger"]

        tx = make_transaction(
            db,
            datetime_utc=datetime(2024, 6, 15, 10, 30, tzinfo=timezone.utc),
            tx_type="deposit",
            to_wallet_id=ledger.id,
            to_amount="0.5",
            to_asset_id=btc.id,
            to_value_usd="25000",
        )

        row = ParsedRow(
            row_number=2,
            to_value_usd="24500",  # different value
            raw_data={},
        )

        _update_existing_from_ledger(db, tx, row, None, ledger.id)

        # Original value preserved
        assert tx.to_value_usd == "25000"


# ---------------------------------------------------------------------------
# Ledger account resolution
# ---------------------------------------------------------------------------


class TestLedgerAccountResolution:
    def test_creates_account_from_description(self, db, seed_wallets):
        """Account is created from Ledger description data."""
        ledger = seed_wallets["Ledger"]

        row = ParsedRow(
            row_number=2,
            description="Account: L1-Ethereum | Address: 0xABCD1234",
        )

        account_id = _resolve_ledger_account(db, row, ledger.id)
        assert account_id is not None

        acct = db.get(Account, account_id)
        assert acct.name == "L1-Ethereum"
        assert acct.address == "0xABCD1234"
        assert acct.blockchain == "ethereum"
        assert acct.wallet_id == ledger.id

    def test_reuses_existing_account_by_address(self, db, seed_wallets):
        """If an account with the same address exists, reuse it."""
        ledger = seed_wallets["Ledger"]

        existing = Account(
            wallet_id=ledger.id,
            name="OldName",
            address="0xABCD1234",
            blockchain="ethereum",
        )
        db.add(existing)
        db.commit()

        row = ParsedRow(
            row_number=2,
            description="Account: L1-Ethereum | Address: 0xABCD1234",
        )

        account_id = _resolve_ledger_account(db, row, ledger.id)
        assert account_id == existing.id

    def test_no_account_without_description(self, db, seed_wallets):
        """Rows without description return None."""
        row = ParsedRow(row_number=2)
        assert _resolve_ledger_account(db, row, seed_wallets["Ledger"].id) is None

    def test_blockchain_detection(self, db, seed_wallets):
        """Blockchain is inferred from account name."""
        ledger = seed_wallets["Ledger"]
        test_cases = [
            ("L1-Bitcoin", "bitcoin"),
            ("L1-Solana", "solana"),
            ("L1-Cosmos", "cosmos"),
            ("L2-Bitcoin", "bitcoin"),
        ]
        for name, expected_chain in test_cases:
            row = ParsedRow(
                row_number=2,
                description=f"Account: {name} | Address: addr_{name}",
            )
            acct_id = _resolve_ledger_account(db, row, ledger.id)
            acct = db.get(Account, acct_id)
            assert acct.blockchain == expected_chain, f"{name} → expected {expected_chain}"


# ---------------------------------------------------------------------------
# Full import flow — end to end
# ---------------------------------------------------------------------------


class TestLedgerImportFlow:
    def test_ledger_import_skips_fees_warning_only(self, db, seed_assets, seed_wallets):
        """Only standalone FEES rows are skipped; DELEGATE is imported."""
        content = (FIXTURES / "ledger_sample.csv").read_text()
        result = parse_csv(content)
        all_rows = result.rows  # includes warnings

        imported, skipped, errors = import_parsed_rows(
            db, all_rows, seed_wallets["Ledger"].id, source="ledger_import"
        )

        # 7 total: 6 valid (incl. DELEGATE as fee), 1 warning (FEES)
        assert skipped >= 1  # standalone FEES row
        assert imported == 6  # 5 original valid + DELEGATE now imported

    def test_ledger_dedup_enriches_existing(self, db, seed_assets, seed_wallets):
        """Existing transactions are enriched, not duplicated."""
        btc = seed_assets["BTC"]
        ledger = seed_wallets["Ledger"]

        # Pre-existing transaction from Koinly import
        existing = make_transaction(
            db,
            datetime_utc=datetime(2024, 6, 15, 10, 30, tzinfo=timezone.utc),
            tx_type="deposit",
            to_wallet_id=ledger.id,
            to_amount="0.5",
            to_asset_id=btc.id,
            to_value_usd="25000",
            tx_hash="abc123hash",
            source="koinly_import",
        )
        existing_id = existing.id

        # Import Ledger CSV
        content = (FIXTURES / "ledger_sample.csv").read_text()
        result = parse_csv(content)

        before_count = db.query(Transaction).count()
        imported, skipped, errors = import_parsed_rows(
            db, result.rows, ledger.id, source="ledger_import"
        )
        after_count = db.query(Transaction).count()

        # The BTC IN row should NOT create a duplicate
        btc_deposits = db.query(Transaction).filter_by(
            tx_hash="abc123hash"
        ).all()
        assert len(btc_deposits) == 1
        assert btc_deposits[0].id == existing_id

    def test_ledger_import_creates_accounts(self, db, seed_assets, seed_wallets):
        """Ledger import creates account records from CSV data."""
        content = (FIXTURES / "ledger_sample.csv").read_text()
        result = parse_csv(content)
        ledger = seed_wallets["Ledger"]

        import_parsed_rows(db, result.rows, ledger.id, source="ledger_import")

        accounts = db.query(Account).filter_by(wallet_id=ledger.id).all()
        account_names = {a.name for a in accounts}

        # Should have created accounts from the fixture
        assert "L1-Bitcoin" in account_names
        assert "L1-Ethereum" in account_names
