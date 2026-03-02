"""Tests for the Koinly full-import service and API endpoints."""

import pytest
from datetime import datetime, timezone

from app.models import Account, Transaction, Wallet
from app.services.koinly_import import (
    KOINLY_WALLET_TYPE_MAP,
    _derive_usd_values,
    confirm_koinly_import,
    parse_transactions_csv,
    parse_wallets_csv,
    preview_koinly_import,
)


# ---------------------------------------------------------------------------
# Sample CSV data
# ---------------------------------------------------------------------------

WALLETS_CSV = """\
Koinly ID,Name,Type,Blockchain,Balance Count
ABC123,Coinbase,exchange,,0
DEF456,Ledger - Bitcoin (BTC),blockchain,Bitcoin,0
GHI789,MetaMask (ETH),wallet,Ethereum,0
JKL012,BlockFi,other,,0
"""

WALLETS_CSV_EMPTY_TYPE = """\
Koinly ID,Name,Type,Blockchain,Balance Count
XYZ999,Mystery Wallet,,,0
"""

TRANSACTIONS_CSV = """\
Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Net Worth Amount,Net Worth Currency,Label,Description,TxHash,Koinly ID,From Wallet,From Wallet ID,To Wallet,To Wallet ID
2026-01-15 10:00:00 UTC,,,0.5,BTC,,,25000.00,USD,crypto_deposit,,0xabc123,TX001,,,Ledger - Bitcoin (BTC),DEF456
2026-01-16 12:00:00 UTC,1.0,ETH,,,,,,USD,crypto_withdrawal,,0xdef456,TX002,MetaMask (ETH),GHI789,,,
2026-01-17 14:00:00 UTC,500,USD,0.01,BTC,5,USD,500,USD,buy,Bought BTC,,TX003,,ABC123,,ABC123
2026-01-18 16:00:00 UTC,0.5,ETH,0.5,STETH,0.001,ETH,1000,EUR,trade,Staked ETH,0xghi789,TX004,MetaMask (ETH),GHI789,MetaMask (ETH),GHI789
"""

TRANSACTIONS_CSV_NO_LABEL = """\
Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Net Worth Amount,Net Worth Currency,Label,Description,TxHash,Koinly ID,From Wallet,From Wallet ID,To Wallet,To Wallet ID
2026-02-01 08:00:00 UTC,,,1.0,SOL,,,50.00,USD,,,0xsol1,TX_NOLABEL,,,Ledger - Bitcoin (BTC),DEF456
"""


def _make_all_new_mapping(preview):
    """Helper: build wallet_mapping that creates a new wallet for each Koinly wallet."""
    return {pw.koinly_id: "new" for pw in preview.wallets}


# ---------------------------------------------------------------------------
# 4.1 Wallet CSV parsing tests
# ---------------------------------------------------------------------------


class TestWalletCsvParsing:
    def test_parse_wallets_basic(self):
        wallets = parse_wallets_csv(WALLETS_CSV)
        assert len(wallets) == 4
        assert wallets[0].koinly_id == "ABC123"
        assert wallets[0].name == "Coinbase"
        assert wallets[0].mapped_type == "exchange"

    def test_wallet_type_mapping_exchange(self):
        wallets = parse_wallets_csv(WALLETS_CSV)
        coinbase = next(w for w in wallets if w.name == "Coinbase")
        assert coinbase.mapped_type == "exchange"

    def test_wallet_type_mapping_blockchain(self):
        wallets = parse_wallets_csv(WALLETS_CSV)
        ledger = next(w for w in wallets if w.koinly_id == "DEF456")
        assert ledger.mapped_type == "hardware"

    def test_wallet_type_mapping_wallet(self):
        wallets = parse_wallets_csv(WALLETS_CSV)
        metamask = next(w for w in wallets if w.koinly_id == "GHI789")
        assert metamask.mapped_type == "software"

    def test_wallet_type_mapping_other(self):
        wallets = parse_wallets_csv(WALLETS_CSV)
        blockfi = next(w for w in wallets if w.koinly_id == "JKL012")
        assert blockfi.mapped_type == "other"

    def test_empty_type_defaults_to_other(self):
        wallets = parse_wallets_csv(WALLETS_CSV_EMPTY_TYPE)
        assert len(wallets) == 1
        assert wallets[0].mapped_type == "other"

    def test_skips_rows_without_koinly_id(self):
        csv = "Koinly ID,Name,Type,Blockchain,Balance Count\n,NoID,exchange,,0\n"
        wallets = parse_wallets_csv(csv)
        assert len(wallets) == 0

    def test_skips_rows_without_name(self):
        csv = "Koinly ID,Name,Type,Blockchain,Balance Count\nABC,,exchange,,0\n"
        wallets = parse_wallets_csv(csv)
        assert len(wallets) == 0

    def test_blockchain_field_parsed(self):
        wallets = parse_wallets_csv(WALLETS_CSV)
        ledger = next(w for w in wallets if w.koinly_id == "DEF456")
        assert ledger.blockchain == "Bitcoin"
        coinbase = next(w for w in wallets if w.koinly_id == "ABC123")
        assert coinbase.blockchain is None


# ---------------------------------------------------------------------------
# 4.2 Transaction CSV parsing tests
# ---------------------------------------------------------------------------


class TestTransactionCsvParsing:
    def test_parse_transactions_basic(self):
        txs = parse_transactions_csv(TRANSACTIONS_CSV)
        assert len(txs) == 4

    def test_label_crypto_deposit_maps_to_deposit(self):
        txs = parse_transactions_csv(TRANSACTIONS_CSV)
        tx = next(t for t in txs if t.koinly_tx_id == "TX001")
        assert tx.tx_type == "deposit"

    def test_label_crypto_withdrawal_maps_to_withdrawal(self):
        txs = parse_transactions_csv(TRANSACTIONS_CSV)
        tx = next(t for t in txs if t.koinly_tx_id == "TX002")
        assert tx.tx_type == "withdrawal"

    def test_label_buy_maps_to_buy(self):
        txs = parse_transactions_csv(TRANSACTIONS_CSV)
        tx = next(t for t in txs if t.koinly_tx_id == "TX003")
        assert tx.tx_type == "buy"

    def test_label_trade_maps_to_trade(self):
        txs = parse_transactions_csv(TRANSACTIONS_CSV)
        tx = next(t for t in txs if t.koinly_tx_id == "TX004")
        assert tx.tx_type == "trade"

    def test_wallet_id_resolution(self):
        txs = parse_transactions_csv(TRANSACTIONS_CSV)
        tx = next(t for t in txs if t.koinly_tx_id == "TX001")
        assert tx.from_wallet_koinly_id is None
        assert tx.to_wallet_koinly_id == "DEF456"

    def test_usd_value_stored(self):
        txs = parse_transactions_csv(TRANSACTIONS_CSV)
        tx = next(t for t in txs if t.koinly_tx_id == "TX001")
        assert tx.net_value_usd == "25000.00"

    def test_non_usd_value_skipped(self):
        txs = parse_transactions_csv(TRANSACTIONS_CSV)
        tx = next(t for t in txs if t.koinly_tx_id == "TX004")
        assert tx.net_value_usd is None  # EUR, not USD

    def test_type_inferred_from_amounts_when_no_label(self):
        txs = parse_transactions_csv(TRANSACTIONS_CSV_NO_LABEL)
        assert len(txs) == 1
        # Only received amount → deposit
        assert txs[0].tx_type == "deposit"

    def test_amounts_parsed(self):
        txs = parse_transactions_csv(TRANSACTIONS_CSV)
        trade = next(t for t in txs if t.koinly_tx_id == "TX004")
        assert trade.from_amount == "0.5"
        assert trade.from_asset == "ETH"
        assert trade.to_amount == "0.5"
        assert trade.to_asset == "STETH"
        assert trade.fee_amount == "0.001"
        assert trade.fee_asset == "ETH"

    def test_bad_date_produces_error(self):
        csv = (
            "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,"
            "Fee Amount,Fee Currency,Net Worth Amount,Net Worth Currency,"
            "Label,Description,TxHash,Koinly ID,From Wallet,From Wallet ID,"
            "To Wallet,To Wallet ID\n"
            "not-a-date,,,1.0,BTC,,,100,USD,deposit,,hash1,TXBAD,,,,\n"
        )
        txs = parse_transactions_csv(csv)
        assert len(txs) == 1
        assert txs[0].status == "error"
        assert "Cannot parse date" in txs[0].error_message


# ---------------------------------------------------------------------------
# 4.3 Preview tests (existing wallets list, transaction dedup)
# ---------------------------------------------------------------------------


class TestPreview:
    def test_preview_returns_existing_wallets_list(self, db, seed_assets):
        # Create an existing wallet
        w = Wallet(name="My Ledger", type="hardware", category="wallet")
        db.add(w)
        db.commit()

        preview = preview_koinly_import(db, WALLETS_CSV, TRANSACTIONS_CSV)
        assert len(preview.existing_wallets_list) == 1
        assert preview.existing_wallets_list[0].name == "My Ledger"
        assert preview.existing_wallets_list[0].id == w.id

    def test_preview_returns_all_koinly_wallets(self, db, seed_assets):
        preview = preview_koinly_import(db, WALLETS_CSV, TRANSACTIONS_CSV)
        assert preview.total_wallets == 4
        assert preview.new_wallets == 4

    def test_transaction_dedup_by_koinly_tx_id(self, db, seed_assets):
        tx = Transaction(
            datetime_utc=datetime(2026, 1, 15, 10, 0, 0),
            type="deposit",
            koinly_tx_id="TX001",
            source="koinly_import",
        )
        db.add(tx)
        db.commit()

        preview = preview_koinly_import(db, WALLETS_CSV, TRANSACTIONS_CSV)
        assert preview.duplicate_transactions >= 1


# ---------------------------------------------------------------------------
# 4.4 Full import flow with wallet mapping & account creation
# ---------------------------------------------------------------------------


class TestFullImportFlow:
    def test_create_new_wallets_and_accounts(self, db, seed_assets):
        """Mapping all to 'new' creates wallets + accounts."""
        preview = preview_koinly_import(db, WALLETS_CSV, TRANSACTIONS_CSV)
        mapping = _make_all_new_mapping(preview)

        w_created, w_skipped, accts_created, t_imported, t_skipped, errors = (
            confirm_koinly_import(db, preview, mapping)
        )
        assert w_created == 4
        assert w_skipped == 0
        assert accts_created == 4
        assert t_imported == 4
        assert t_skipped == 0
        assert errors == []

        # Verify accounts in DB
        accounts = db.query(Account).all()
        assert len(accounts) == 4
        # Account names should be the Koinly IDs
        names = {a.name for a in accounts}
        assert names == {"ABC123", "DEF456", "GHI789", "JKL012"}

    def test_accounts_have_correct_blockchain(self, db, seed_assets):
        preview = preview_koinly_import(db, WALLETS_CSV, TRANSACTIONS_CSV)
        mapping = _make_all_new_mapping(preview)
        confirm_koinly_import(db, preview, mapping)

        ledger_acct = db.query(Account).filter_by(name="DEF456").first()
        assert ledger_acct.blockchain == "Bitcoin"

        metamask_acct = db.query(Account).filter_by(name="GHI789").first()
        assert metamask_acct.blockchain == "Ethereum"

        # No blockchain in CSV → "unknown"
        coinbase_acct = db.query(Account).filter_by(name="ABC123").first()
        assert coinbase_acct.blockchain == "unknown"

    def test_accounts_have_empty_address(self, db, seed_assets):
        preview = preview_koinly_import(db, WALLETS_CSV, TRANSACTIONS_CSV)
        mapping = _make_all_new_mapping(preview)
        confirm_koinly_import(db, preview, mapping)

        for acct in db.query(Account).all():
            assert acct.address == ""

    def test_map_to_existing_wallet(self, db, seed_assets):
        """Mapping to an existing wallet ID creates account under it."""
        existing = Wallet(name="My Ledger", type="hardware", category="wallet")
        db.add(existing)
        db.commit()
        db.refresh(existing)

        preview = preview_koinly_import(db, WALLETS_CSV, TRANSACTIONS_CSV)
        mapping = _make_all_new_mapping(preview)
        # Map DEF456 to the existing wallet instead of creating new
        mapping["DEF456"] = existing.id

        w_created, w_skipped, accts_created, t_imported, t_skipped, errors = (
            confirm_koinly_import(db, preview, mapping)
        )
        assert w_created == 3  # 3 new (ABC123, GHI789, JKL012)
        assert w_skipped == 1  # DEF456 reused existing
        assert accts_created == 4  # All 4 accounts created

        # The DEF456 account should be under the existing wallet
        acct = db.query(Account).filter_by(name="DEF456").first()
        assert acct.wallet_id == existing.id

    def test_transactions_linked_to_accounts(self, db, seed_assets):
        """Transactions have correct from_account_id / to_account_id."""
        preview = preview_koinly_import(db, WALLETS_CSV, TRANSACTIONS_CSV)
        mapping = _make_all_new_mapping(preview)
        confirm_koinly_import(db, preview, mapping)

        # TX001: deposit to DEF456
        tx1 = db.query(Transaction).filter_by(koinly_tx_id="TX001").first()
        ledger_acct = db.query(Account).filter_by(name="DEF456").first()
        assert tx1.to_account_id == ledger_acct.id
        assert tx1.to_wallet_id == ledger_acct.wallet_id
        assert tx1.from_account_id is None
        assert tx1.from_wallet_id is None

        # TX002: withdrawal from GHI789
        tx2 = db.query(Transaction).filter_by(koinly_tx_id="TX002").first()
        metamask_acct = db.query(Account).filter_by(name="GHI789").first()
        assert tx2.from_account_id == metamask_acct.id
        assert tx2.from_wallet_id == metamask_acct.wallet_id
        assert tx2.to_account_id is None

        # TX004: trade from GHI789 to GHI789 (same wallet)
        tx4 = db.query(Transaction).filter_by(koinly_tx_id="TX004").first()
        assert tx4.from_account_id == metamask_acct.id
        assert tx4.to_account_id == metamask_acct.id

    def test_transactions_also_linked_to_wallets(self, db, seed_assets):
        """from_wallet_id / to_wallet_id are set from account's parent wallet."""
        preview = preview_koinly_import(db, WALLETS_CSV, TRANSACTIONS_CSV)
        mapping = _make_all_new_mapping(preview)
        confirm_koinly_import(db, preview, mapping)

        tx1 = db.query(Transaction).filter_by(koinly_tx_id="TX001").first()
        ledger_wallet = db.query(Wallet).filter_by(koinly_wallet_id="DEF456").first()
        assert tx1.to_wallet_id == ledger_wallet.id

    def test_duplicate_account_not_recreated(self, db, seed_assets):
        """If account with same name exists under wallet, reuse it."""
        existing_wallet = Wallet(name="Existing", type="exchange", category="exchange")
        db.add(existing_wallet)
        db.flush()
        existing_acct = Account(
            wallet_id=existing_wallet.id, name="ABC123", address="", blockchain="unknown"
        )
        db.add(existing_acct)
        db.commit()
        db.refresh(existing_acct)

        preview = preview_koinly_import(db, WALLETS_CSV, TRANSACTIONS_CSV)
        mapping = _make_all_new_mapping(preview)
        mapping["ABC123"] = existing_wallet.id

        w_created, w_skipped, accts_created, t_imported, t_skipped, errors = (
            confirm_koinly_import(db, preview, mapping)
        )
        # ABC123 account already exists → not re-created
        assert accts_created == 3

    def test_assets_auto_created(self, db):
        """Assets referenced in CSV that don't exist should be auto-created."""
        preview = preview_koinly_import(db, WALLETS_CSV, TRANSACTIONS_CSV)
        mapping = _make_all_new_mapping(preview)
        confirm_koinly_import(db, preview, mapping)

        from app.models import Asset
        btc = db.query(Asset).filter_by(symbol="BTC").first()
        assert btc is not None
        steth = db.query(Asset).filter_by(symbol="STETH").first()
        assert steth is not None

    def test_koinly_wallet_in_tx_but_missing_from_csv(self, db, seed_assets):
        """Transactions referencing unknown wallet IDs get null account/wallet."""
        # Use a transactions CSV that references a wallet not in the wallets CSV
        tx_csv = """\
Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Net Worth Amount,Net Worth Currency,Label,Description,TxHash,Koinly ID,From Wallet,From Wallet ID,To Wallet,To Wallet ID
2026-01-15 10:00:00 UTC,,,0.5,BTC,,,25000.00,USD,deposit,,0xabc,TX_MISS,,,Unknown Wallet,UNKNOWN999
"""
        preview = preview_koinly_import(db, WALLETS_CSV, tx_csv)
        mapping = _make_all_new_mapping(preview)
        w_created, w_skipped, accts_created, t_imported, t_skipped, errors = (
            confirm_koinly_import(db, preview, mapping)
        )

        # Transaction should still be imported, just with null wallet/account
        tx = db.query(Transaction).filter_by(koinly_tx_id="TX_MISS").first()
        assert tx is not None
        assert tx.to_account_id is None
        assert tx.to_wallet_id is None


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestKoinlyImportApi:
    def test_upload_and_confirm(self, client, db, seed_assets, seed_settings):
        """End-to-end API test: upload → preview → confirm with mapping."""
        # Upload
        resp = client.post(
            "/api/import/koinly",
            files={
                "wallets_file": ("wallets.csv", WALLETS_CSV, "text/csv"),
                "transactions_file": ("transactions.csv", TRANSACTIONS_CSV, "text/csv"),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_wallets"] == 4
        assert data["new_wallets"] == 4
        assert data["total_transactions"] == 4
        assert "existing_wallets_list" in data

        # Confirm with all-new mapping
        mapping = {w["koinly_id"]: "new" for w in data["wallets"]}
        resp2 = client.post(
            "/api/import/koinly/confirm",
            json={"wallet_mapping": mapping},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["wallets_created"] == 4
        assert data2["accounts_created"] == 4
        assert data2["transactions_imported"] == 4

    def test_confirm_without_preview_returns_404(self, client, db, seed_assets, seed_settings):
        resp = client.post(
            "/api/import/koinly/confirm",
            json={"wallet_mapping": {}},
        )
        assert resp.status_code == 404

    def test_confirm_with_missing_mapping_returns_400(self, client, db, seed_assets, seed_settings):
        """Confirm with incomplete mapping should fail."""
        # Upload first
        client.post(
            "/api/import/koinly",
            files={
                "wallets_file": ("wallets.csv", WALLETS_CSV, "text/csv"),
                "transactions_file": ("transactions.csv", TRANSACTIONS_CSV, "text/csv"),
            },
        )
        # Confirm with only partial mapping
        resp = client.post(
            "/api/import/koinly/confirm",
            json={"wallet_mapping": {"ABC123": "new"}},
        )
        assert resp.status_code == 400
        assert "Missing wallet mapping" in resp.json()["detail"]

    def test_confirm_with_existing_wallet_mapping(self, client, db, seed_assets, seed_settings):
        """Map Koinly wallets to existing wallet."""
        # Create an existing wallet
        w = Wallet(name="My Exchange", type="exchange", category="exchange")
        db.add(w)
        db.commit()
        db.refresh(w)

        # Upload
        resp = client.post(
            "/api/import/koinly",
            files={
                "wallets_file": ("wallets.csv", WALLETS_CSV, "text/csv"),
                "transactions_file": ("transactions.csv", TRANSACTIONS_CSV, "text/csv"),
            },
        )
        data = resp.json()

        # Map all to existing wallet
        mapping = {wd["koinly_id"]: w.id for wd in data["wallets"]}
        resp2 = client.post(
            "/api/import/koinly/confirm",
            json={"wallet_mapping": mapping},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["wallets_created"] == 0
        assert data2["wallets_skipped"] == 4
        assert data2["accounts_created"] == 4


# ---------------------------------------------------------------------------
# 4.5 USD value derivation tests
# ---------------------------------------------------------------------------


class TestUsdValueDerivation:
    def test_buy_derives_to_value_usd(self):
        """Parsed buy has to_value_usd derived from net_value_usd."""
        txs = parse_transactions_csv(TRANSACTIONS_CSV)
        buy_tx = next(t for t in txs if t.koinly_tx_id == "TX003")
        assert buy_tx.tx_type == "buy"
        assert buy_tx.net_value_usd == "500"
        assert buy_tx.to_value_usd == "500"

    def test_sell_derives_from_value_usd(self):
        """Parsed sell has from_value_usd derived from net_value_usd."""
        csv = """\
Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Net Worth Amount,Net Worth Currency,Label,Description,TxHash,Koinly ID,From Wallet,From Wallet ID,To Wallet,To Wallet ID
2026-01-20 10:00:00 UTC,0.5,BTC,15000,USD,,,15000,USD,sell,Sold BTC,,TX_SELL,Coinbase,ABC123,,
"""
        txs = parse_transactions_csv(csv)
        assert len(txs) == 1
        assert txs[0].tx_type == "sell"
        assert txs[0].from_value_usd == "15000"
        assert txs[0].to_value_usd is None

    def test_deposit_derives_to_value_usd(self):
        """Parsed deposit has to_value_usd from net_value_usd."""
        txs = parse_transactions_csv(TRANSACTIONS_CSV)
        deposit_tx = next(t for t in txs if t.koinly_tx_id == "TX001")
        assert deposit_tx.tx_type == "deposit"
        assert deposit_tx.to_value_usd == "25000.00"

    def test_transfer_derives_both(self):
        """Parsed transfer has both from_value_usd and to_value_usd."""
        csv = """\
Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Net Worth Amount,Net Worth Currency,Label,Description,TxHash,Koinly ID,From Wallet,From Wallet ID,To Wallet,To Wallet ID
2026-01-20 10:00:00 UTC,1.0,BTC,1.0,BTC,,,30000,USD,transfer,Transfer,,TX_XFER,Coinbase,ABC123,Ledger,DEF456
"""
        txs = parse_transactions_csv(csv)
        assert len(txs) == 1
        assert txs[0].tx_type == "transfer"
        assert txs[0].from_value_usd == "30000"
        assert txs[0].to_value_usd == "30000"

    def test_non_usd_does_not_derive(self):
        """Non-USD net_value doesn't get derived (net_value_usd is None)."""
        txs = parse_transactions_csv(TRANSACTIONS_CSV)
        trade_tx = next(t for t in txs if t.koinly_tx_id == "TX004")
        assert trade_tx.net_value_usd is None
        assert trade_tx.from_value_usd is None
        assert trade_tx.to_value_usd is None

    def test_confirm_passes_derived_values(self, db, seed_assets):
        """Confirmed import stores from_value_usd / to_value_usd on Transaction rows."""
        preview = preview_koinly_import(db, WALLETS_CSV, TRANSACTIONS_CSV)
        mapping = _make_all_new_mapping(preview)
        confirm_koinly_import(db, preview, mapping)

        # TX001 is a deposit → to_value_usd should be set
        tx1 = db.query(Transaction).filter_by(koinly_tx_id="TX001").first()
        assert tx1.to_value_usd == "25000.00"
        assert tx1.from_value_usd is None

        # TX003 is a buy → to_value_usd should be set
        tx3 = db.query(Transaction).filter_by(koinly_tx_id="TX003").first()
        assert tx3.to_value_usd == "500"
