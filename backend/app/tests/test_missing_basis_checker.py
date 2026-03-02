"""Tests for missing_basis_checker — zero-cost-basis detection and deposit orphan detection."""

from datetime import datetime, timezone
from decimal import Decimal

from app.models import TransactionType
from app.services.missing_basis_checker import find_missing_basis
from app.tests.factories import create_asset, create_wallet, create_transaction, create_tax_lot


class TestZeroBasisDetection:
    def test_flags_zero_basis_purchase(self, db):
        """A purchase lot with $0 cost basis is flagged."""
        wallet = create_wallet(db, name="Coinbase")
        btc = create_asset(db, symbol="BTC")
        tx = create_transaction(
            db, tx_type="buy", to_wallet_id=wallet.id,
            to_asset_id=btc.id, to_amount="1.0",
        )
        db.commit()

        create_tax_lot(
            db, wallet_id=wallet.id, asset_id=btc.id,
            amount="1.0", cost_basis_usd="0.00",
            acquisition_tx_id=tx.id, source_type="purchase",
        )
        db.commit()

        results = find_missing_basis(db)
        purchase_results = [r for r in results if "Zero cost basis" in r["reason"]]
        assert len(purchase_results) == 1
        assert purchase_results[0]["asset_symbol"] == "BTC"
        assert purchase_results[0]["wallet_name"] == "Coinbase"

    def test_skips_legitimate_airdrop(self, db):
        """Airdrop lot with $0 basis is NOT flagged."""
        wallet = create_wallet(db, name="Ledger")
        sol = create_asset(db, symbol="SOL")
        tx = create_transaction(
            db, tx_type="airdrop", to_wallet_id=wallet.id,
            to_asset_id=sol.id, to_amount="100.0",
        )
        db.commit()

        create_tax_lot(
            db, wallet_id=wallet.id, asset_id=sol.id,
            amount="100.0", cost_basis_usd="0.00",
            acquisition_tx_id=tx.id, source_type="airdrop",
        )
        db.commit()

        results = find_missing_basis(db)
        zero_basis_results = [r for r in results if "Zero cost basis" in r["reason"]]
        assert len(zero_basis_results) == 0

    def test_skips_legitimate_fork(self, db):
        """Fork lot with $0 basis is NOT flagged."""
        wallet = create_wallet(db, name="Ledger")
        bch = create_asset(db, symbol="BCH")
        tx = create_transaction(
            db, tx_type="fork", to_wallet_id=wallet.id,
            to_asset_id=bch.id, to_amount="1.0",
        )
        db.commit()

        create_tax_lot(
            db, wallet_id=wallet.id, asset_id=bch.id,
            amount="1.0", cost_basis_usd="0.00",
            acquisition_tx_id=tx.id, source_type="fork",
        )
        db.commit()

        results = find_missing_basis(db)
        zero_basis_results = [r for r in results if "Zero cost basis" in r["reason"]]
        assert len(zero_basis_results) == 0

    def test_skips_legitimate_gift(self, db):
        """Gift lot with $0 basis is NOT flagged."""
        wallet = create_wallet(db, name="Ledger")
        eth = create_asset(db, symbol="ETH")
        tx = create_transaction(
            db, tx_type="gift", to_wallet_id=wallet.id,
            to_asset_id=eth.id, to_amount="1.0",
        )
        db.commit()

        create_tax_lot(
            db, wallet_id=wallet.id, asset_id=eth.id,
            amount="1.0", cost_basis_usd="0.00",
            acquisition_tx_id=tx.id, source_type="gift",
        )
        db.commit()

        results = find_missing_basis(db)
        zero_basis_results = [r for r in results if "Zero cost basis" in r["reason"]]
        assert len(zero_basis_results) == 0

    def test_nonzero_basis_not_flagged(self, db):
        """A lot with $500 cost basis is never flagged."""
        wallet = create_wallet(db, name="Coinbase")
        btc = create_asset(db, symbol="BTC")
        tx = create_transaction(
            db, tx_type="buy", to_wallet_id=wallet.id,
            to_asset_id=btc.id, to_amount="0.01",
        )
        db.commit()

        create_tax_lot(
            db, wallet_id=wallet.id, asset_id=btc.id,
            amount="0.01", cost_basis_usd="500.00",
            acquisition_tx_id=tx.id, source_type="purchase",
        )
        db.commit()

        results = find_missing_basis(db)
        zero_basis_results = [r for r in results if "Zero cost basis" in r["reason"]]
        assert len(zero_basis_results) == 0


class TestDepositOrphanDetection:
    def test_deposit_without_matching_outbound(self, db):
        """Deposit with no matching withdrawal is flagged as orphan."""
        wallet = create_wallet(db, name="Ledger")
        btc = create_asset(db, symbol="BTC")
        db.commit()

        create_transaction(
            db, tx_type="deposit",
            datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            to_wallet_id=wallet.id, to_asset_id=btc.id,
            to_amount="0.5",
        )
        db.commit()

        results = find_missing_basis(db)
        orphan_results = [r for r in results if "no matching outbound" in r["reason"]]
        assert len(orphan_results) == 1
        assert orphan_results[0]["asset_symbol"] == "BTC"
        assert orphan_results[0]["wallet_name"] == "Ledger"
        assert orphan_results[0]["lot_id"] is None

    def test_deposit_with_matching_withdrawal(self, db):
        """Deposit that has a matching withdrawal is NOT flagged."""
        wallet_src = create_wallet(db, name="Coinbase")
        wallet_dst = create_wallet(db, name="Ledger")
        btc = create_asset(db, symbol="BTC")
        db.commit()

        # Withdrawal from source wallet
        create_transaction(
            db, tx_type="withdrawal",
            datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            from_wallet_id=wallet_src.id, from_asset_id=btc.id,
            from_amount="0.5",
        )
        # Deposit to destination wallet (same amount, same asset)
        create_transaction(
            db, tx_type="deposit",
            datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            to_wallet_id=wallet_dst.id, to_asset_id=btc.id,
            to_amount="0.5",
        )
        db.commit()

        results = find_missing_basis(db)
        orphan_results = [r for r in results if "no matching outbound" in r["reason"]]
        assert len(orphan_results) == 0

    def test_deposit_with_matching_transfer(self, db):
        """Deposit that has a matching transfer is NOT flagged."""
        wallet_src = create_wallet(db, name="Coinbase")
        wallet_dst = create_wallet(db, name="Ledger")
        btc = create_asset(db, symbol="BTC")
        db.commit()

        # Transfer from source wallet
        create_transaction(
            db, tx_type="transfer",
            datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            from_wallet_id=wallet_src.id, from_asset_id=btc.id,
            from_amount="1.0",
            to_wallet_id=wallet_dst.id, to_asset_id=btc.id,
            to_amount="1.0",
        )
        # Also a deposit recorded
        create_transaction(
            db, tx_type="deposit",
            datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            to_wallet_id=wallet_dst.id, to_asset_id=btc.id,
            to_amount="1.0",
        )
        db.commit()

        results = find_missing_basis(db)
        orphan_results = [r for r in results if "no matching outbound" in r["reason"]]
        assert len(orphan_results) == 0

    def test_deposit_missing_wallet_id_skipped(self, db):
        """Deposit with no to_wallet_id is skipped (not flagged)."""
        btc = create_asset(db, symbol="BTC")
        db.commit()

        create_transaction(
            db, tx_type="deposit",
            datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            to_asset_id=btc.id, to_amount="0.5",
            # No to_wallet_id
        )
        db.commit()

        results = find_missing_basis(db)
        orphan_results = [r for r in results if "no matching outbound" in r["reason"]]
        assert len(orphan_results) == 0

    def test_deposit_missing_asset_id_skipped(self, db):
        """Deposit with no to_asset_id is skipped."""
        wallet = create_wallet(db, name="Ledger")
        db.commit()

        create_transaction(
            db, tx_type="deposit",
            datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            to_wallet_id=wallet.id, to_amount="0.5",
            # No to_asset_id
        )
        db.commit()

        results = find_missing_basis(db)
        orphan_results = [r for r in results if "no matching outbound" in r["reason"]]
        assert len(orphan_results) == 0

    def test_deposit_no_to_amount(self, db):
        """Deposit with no to_amount is flagged (can't find matching)."""
        wallet = create_wallet(db, name="Ledger")
        btc = create_asset(db, symbol="BTC")
        db.commit()

        create_transaction(
            db, tx_type="deposit",
            datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            to_wallet_id=wallet.id, to_asset_id=btc.id,
            # No to_amount
        )
        db.commit()

        results = find_missing_basis(db)
        orphan_results = [r for r in results if "no matching outbound" in r["reason"]]
        assert len(orphan_results) == 1
        assert orphan_results[0]["amount"] == "0"
