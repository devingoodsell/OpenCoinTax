"""Tests for Audit & Validation enhancements (Epic 10).

Covers:
- Balance reconciliation (matching data and discrepancy detection)
- Missing cost basis detection (zero-basis lots and airdrop exclusion)
- Audit API endpoints
"""

from datetime import datetime, timezone
from decimal import Decimal

from app.models import TaxLot, LotAssignment, TransactionType
from app.services.balance_reconciler import reconcile_balances
from app.services.missing_basis_checker import find_missing_basis
from app.services.tax_engine import calculate_for_wallet_asset
from app.tests.conftest import make_transaction


# ---------------------------------------------------------------------------
# Balance Reconciliation Tests
# ---------------------------------------------------------------------------


class TestReconcileBalancesMatching:
    """When tax engine runs correctly, lots should match expected balances."""

    def test_no_discrepancy_after_clean_calculation(
        self, db, seed_wallets, seed_assets, seed_settings
    ):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        # Buy 2 BTC
        make_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=w.id,
            to_amount="2.0",
            to_asset_id=btc.id,
            to_value_usd="60000.00",
        )

        # Sell 0.5 BTC
        make_transaction(
            db,
            datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell",
            from_wallet_id=w.id,
            from_amount="0.5",
            from_asset_id=btc.id,
            from_value_usd="25000.00",
        )

        calculate_for_wallet_asset(db, w.id, btc.id, 2025)
        db.commit()

        results = reconcile_balances(db)
        assert len(results) >= 1

        btc_result = [r for r in results if r["asset_id"] == btc.id and r["wallet_id"] == w.id]
        assert len(btc_result) == 1
        r = btc_result[0]
        assert r["is_discrepancy"] is False
        assert r["wallet_name"] == "Coinbase"
        assert r["asset_symbol"] == "BTC"
        assert Decimal(r["expected_balance"]) == Decimal("1.5")
        assert Decimal(r["lot_balance"]) == Decimal("1.5")
        assert Decimal(r["difference"]) == Decimal("0")


class TestReconcileBalancesDiscrepancy:
    """When a lot is tampered with, reconciliation should detect the discrepancy."""

    def test_detects_tampered_lot(
        self, db, seed_wallets, seed_assets, seed_settings
    ):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=w.id,
            to_amount="2.0",
            to_asset_id=btc.id,
            to_value_usd="60000.00",
        )

        make_transaction(
            db,
            datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="sell",
            from_wallet_id=w.id,
            from_amount="0.5",
            from_asset_id=btc.id,
            from_value_usd="25000.00",
        )

        calculate_for_wallet_asset(db, w.id, btc.id, 2025)
        db.commit()

        # Tamper: change the remaining_amount on the lot
        lot = db.query(TaxLot).filter(
            TaxLot.wallet_id == w.id,
            TaxLot.asset_id == btc.id,
        ).first()
        lot.remaining_amount = "0.5"  # Should be 1.5
        db.commit()

        results = reconcile_balances(db)
        btc_result = [r for r in results if r["asset_id"] == btc.id and r["wallet_id"] == w.id]
        assert len(btc_result) == 1
        r = btc_result[0]
        assert r["is_discrepancy"] is True
        assert Decimal(r["difference"]) != Decimal("0")


# ---------------------------------------------------------------------------
# Missing Cost Basis Tests
# ---------------------------------------------------------------------------


class TestFindMissingBasisZeroPurchase:
    """A purchase lot with $0 cost basis should be flagged."""

    def test_zero_basis_purchase_flagged(
        self, db, seed_wallets, seed_assets, seed_settings
    ):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        # Create a buy transaction
        tx = make_transaction(
            db,
            datetime_utc=datetime(2025, 3, 15, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=w.id,
            to_amount="1.0",
            to_asset_id=btc.id,
            to_value_usd="0.00",
        )

        # Manually create a lot with zero cost basis and source_type "purchase"
        lot = TaxLot(
            wallet_id=w.id,
            asset_id=btc.id,
            amount="1.0",
            remaining_amount="1.0",
            cost_basis_usd="0.00",
            cost_basis_per_unit="0.00",
            acquired_date=tx.datetime_utc,
            acquisition_tx_id=tx.id,
            source_type="purchase",
        )
        db.add(lot)
        db.commit()

        results = find_missing_basis(db)
        purchase_flags = [
            r for r in results
            if r["lot_id"] is not None and r["reason"].startswith("Zero cost basis")
        ]
        assert len(purchase_flags) >= 1
        assert purchase_flags[0]["asset_symbol"] == "BTC"
        assert purchase_flags[0]["wallet_name"] == "Coinbase"


class TestFindMissingBasisExcludesAirdrops:
    """Airdrops legitimately have $0 cost basis and should NOT be flagged."""

    def test_airdrop_not_flagged(
        self, db, seed_wallets, seed_assets, seed_settings
    ):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        tx = make_transaction(
            db,
            datetime_utc=datetime(2025, 4, 1, tzinfo=timezone.utc),
            tx_type="airdrop",
            to_wallet_id=w.id,
            to_amount="0.01",
            to_asset_id=btc.id,
            to_value_usd="0.00",
        )

        lot = TaxLot(
            wallet_id=w.id,
            asset_id=btc.id,
            amount="0.01",
            remaining_amount="0.01",
            cost_basis_usd="0.00",
            cost_basis_per_unit="0.00",
            acquired_date=tx.datetime_utc,
            acquisition_tx_id=tx.id,
            source_type="airdrop",
        )
        db.add(lot)
        db.commit()

        results = find_missing_basis(db)
        # Filter to only lot-based flags (not deposit orphan flags)
        lot_flags = [r for r in results if r["lot_id"] is not None]
        assert len(lot_flags) == 0


class TestFindMissingBasisExcludesForksAndGifts:
    """Forks and gifts also legitimately have $0 cost basis."""

    def test_fork_not_flagged(
        self, db, seed_wallets, seed_assets, seed_settings
    ):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        tx = make_transaction(
            db,
            datetime_utc=datetime(2025, 5, 1, tzinfo=timezone.utc),
            tx_type="fork",
            to_wallet_id=w.id,
            to_amount="1.0",
            to_asset_id=btc.id,
            to_value_usd="0.00",
        )

        lot = TaxLot(
            wallet_id=w.id,
            asset_id=btc.id,
            amount="1.0",
            remaining_amount="1.0",
            cost_basis_usd="0.00",
            cost_basis_per_unit="0.00",
            acquired_date=tx.datetime_utc,
            acquisition_tx_id=tx.id,
            source_type="fork",
        )
        db.add(lot)
        db.commit()

        results = find_missing_basis(db)
        lot_flags = [r for r in results if r["lot_id"] is not None]
        assert len(lot_flags) == 0

    def test_gift_not_flagged(
        self, db, seed_wallets, seed_assets, seed_settings
    ):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        tx = make_transaction(
            db,
            datetime_utc=datetime(2025, 5, 1, tzinfo=timezone.utc),
            tx_type="gift_received",
            to_wallet_id=w.id,
            to_amount="0.5",
            to_asset_id=btc.id,
            to_value_usd="0.00",
        )

        lot = TaxLot(
            wallet_id=w.id,
            asset_id=btc.id,
            amount="0.5",
            remaining_amount="0.5",
            cost_basis_usd="0.00",
            cost_basis_per_unit="0.00",
            acquired_date=tx.datetime_utc,
            acquisition_tx_id=tx.id,
            source_type="gift",
        )
        db.add(lot)
        db.commit()

        results = find_missing_basis(db)
        lot_flags = [r for r in results if r["lot_id"] is not None]
        assert len(lot_flags) == 0


# ---------------------------------------------------------------------------
# API Endpoint Tests
# ---------------------------------------------------------------------------


class TestAuditReconciliationEndpoint:
    def test_returns_reconciliation_data(
        self, client, db, seed_wallets, seed_assets, seed_settings
    ):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=w.id,
            to_amount="1.0",
            to_asset_id=btc.id,
            to_value_usd="30000.00",
        )

        calculate_for_wallet_asset(db, w.id, btc.id, 2025)
        db.commit()

        resp = client.get("/api/audit/reconciliation")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert "discrepancy_count" in data
        assert data["discrepancy_count"] == 0


class TestAuditMissingBasisEndpoint:
    def test_returns_missing_basis_data(
        self, client, db, seed_wallets, seed_assets, seed_settings
    ):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        tx = make_transaction(
            db,
            datetime_utc=datetime(2025, 3, 15, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=w.id,
            to_amount="1.0",
            to_asset_id=btc.id,
            to_value_usd="0.00",
        )

        lot = TaxLot(
            wallet_id=w.id,
            asset_id=btc.id,
            amount="1.0",
            remaining_amount="1.0",
            cost_basis_usd="0.00",
            cost_basis_per_unit="0.00",
            acquired_date=tx.datetime_utc,
            acquisition_tx_id=tx.id,
            source_type="purchase",
        )
        db.add(lot)
        db.commit()

        resp = client.get("/api/audit/missing-basis")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1


class TestAuditSummaryEndpoint:
    def test_returns_summary_structure(
        self, client, db, seed_wallets, seed_assets, seed_settings
    ):
        resp = client.get("/api/audit/summary")
        assert resp.status_code == 200
        data = resp.json()

        # Verify top-level structure
        assert "invariant_checks" in data
        assert "reconciliation" in data
        assert "missing_basis" in data
        assert "overall_status" in data

        # Verify sub-structures
        assert "total" in data["invariant_checks"]
        assert "passed" in data["invariant_checks"]
        assert "failed" in data["invariant_checks"]
        assert "pairs_checked" in data["reconciliation"]
        assert "discrepancies" in data["reconciliation"]
        assert "warnings" in data["missing_basis"]

    def test_clean_data_shows_clean_status(
        self, client, db, seed_wallets, seed_assets, seed_settings
    ):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        make_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=w.id,
            to_amount="1.0",
            to_asset_id=btc.id,
            to_value_usd="30000.00",
        )

        calculate_for_wallet_asset(db, w.id, btc.id, 2025)
        db.commit()

        resp = client.get("/api/audit/summary")
        data = resp.json()
        assert data["overall_status"] == "clean"
        assert data["invariant_checks"]["failed"] == 0
        assert data["reconciliation"]["discrepancies"] == 0
        assert data["missing_basis"]["warnings"] == 0

    def test_issues_found_status_with_bad_data(
        self, client, db, seed_wallets, seed_assets, seed_settings
    ):
        w = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]

        tx = make_transaction(
            db,
            datetime_utc=datetime(2025, 3, 15, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=w.id,
            to_amount="1.0",
            to_asset_id=btc.id,
            to_value_usd="0.00",
        )

        lot = TaxLot(
            wallet_id=w.id,
            asset_id=btc.id,
            amount="1.0",
            remaining_amount="1.0",
            cost_basis_usd="0.00",
            cost_basis_per_unit="0.00",
            acquired_date=tx.datetime_utc,
            acquisition_tx_id=tx.id,
            source_type="purchase",
        )
        db.add(lot)
        db.commit()

        resp = client.get("/api/audit/summary")
        data = resp.json()
        assert data["overall_status"] == "issues_found"
        assert data["missing_basis"]["warnings"] >= 1
