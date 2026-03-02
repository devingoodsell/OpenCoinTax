"""Tests for deposit_reclassifier — reclassify crypto_deposit transactions."""

from datetime import datetime, timezone

from app.models import Transaction
from app.services.deposit_reclassifier import reclassify_crypto_deposits
from app.tests.factories import create_asset, create_wallet, create_transaction


class TestReclassifyCryptoDeposits:
    def test_reclassify_staking_token(self, db):
        """STETH deposit is reclassified as staking_reward."""
        wallet = create_wallet(db, name="Ledger")
        steth = create_asset(db, symbol="STETH")
        db.commit()

        create_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="deposit",
            to_wallet_id=wallet.id,
            to_asset_id=steth.id,
            to_amount="0.5",
            label="crypto_deposit",
        )
        db.commit()

        changes = reclassify_crypto_deposits(db, dry_run=True)
        assert len(changes) == 1
        assert changes[0]["new_type"] == "staking_reward"
        assert "liquid staking" in changes[0]["reason"]

    def test_reclassify_interest_by_description(self, db):
        """Deposit with interest keyword in description → interest."""
        wallet = create_wallet(db, name="Coinbase")
        usdc = create_asset(db, symbol="USDC")
        db.commit()

        create_transaction(
            db,
            datetime_utc=datetime(2025, 2, 1, tzinfo=timezone.utc),
            tx_type="deposit",
            to_wallet_id=wallet.id,
            to_asset_id=usdc.id,
            to_amount="10.00",
            description="Interest payment from lending pool",
            label="crypto_deposit",
        )
        db.commit()

        changes = reclassify_crypto_deposits(db, dry_run=True)
        assert len(changes) == 1
        assert changes[0]["new_type"] == "interest"

    def test_skip_non_crypto_deposit(self, db):
        """Regular deposit (no crypto_deposit label) is not reclassified."""
        wallet = create_wallet(db, name="Coinbase")
        btc = create_asset(db, symbol="BTC")
        db.commit()

        create_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="deposit",
            to_wallet_id=wallet.id,
            to_asset_id=btc.id,
            to_amount="1.0",
        )
        db.commit()

        changes = reclassify_crypto_deposits(db, dry_run=True)
        assert len(changes) == 0

    def test_dry_run_does_not_modify(self, db):
        """Dry run returns changes but doesn't update DB."""
        wallet = create_wallet(db, name="Ledger")
        steth = create_asset(db, symbol="STETH")
        db.commit()

        create_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="deposit",
            to_wallet_id=wallet.id,
            to_asset_id=steth.id,
            to_amount="0.5",
            label="crypto_deposit",
        )
        db.commit()

        changes = reclassify_crypto_deposits(db, dry_run=True)
        assert len(changes) == 1

        # DB should not be modified
        tx = db.query(Transaction).first()
        assert tx.type == "deposit"

    def test_apply_changes(self, db):
        """When dry_run=False, transactions are updated."""
        wallet = create_wallet(db, name="Ledger")
        steth = create_asset(db, symbol="STETH")
        db.commit()

        create_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="deposit",
            to_wallet_id=wallet.id,
            to_asset_id=steth.id,
            to_amount="0.5",
            label="crypto_deposit",
        )
        db.commit()

        changes = reclassify_crypto_deposits(db, dry_run=False)
        assert len(changes) == 1

        tx = db.query(Transaction).first()
        assert tx.type == "staking_reward"

    def test_high_frequency_threshold(self, db):
        """7+ deposits of same asset/wallet/year → staking_reward."""
        wallet = create_wallet(db, name="Cosmos Hub")
        atom = create_asset(db, symbol="ATOM")
        db.commit()

        for i in range(8):
            create_transaction(
                db,
                datetime_utc=datetime(2025, 1, i + 1, tzinfo=timezone.utc),
                tx_type="deposit",
                to_wallet_id=wallet.id,
                to_asset_id=atom.id,
                to_amount="0.1",
                to_value_usd="1.00",
                label="crypto_deposit",
            )
        db.commit()

        changes = reclassify_crypto_deposits(db, dry_run=True)
        assert len(changes) == 8
        assert all(c["new_type"] == "staking_reward" for c in changes)
        assert "high-frequency" in changes[0]["reason"]

    def test_below_high_frequency_threshold(self, db):
        """6 deposits (below 7) is not high-frequency reclassification."""
        wallet = create_wallet(db, name="Cosmos Hub")
        atom = create_asset(db, symbol="ATOM")
        db.commit()

        for i in range(6):
            create_transaction(
                db,
                datetime_utc=datetime(2025, 1, i + 1, tzinfo=timezone.utc),
                tx_type="deposit",
                to_wallet_id=wallet.id,
                to_asset_id=atom.id,
                to_amount="1.0",
                to_value_usd="100.00",
                label="crypto_deposit",
            )
        db.commit()

        changes = reclassify_crypto_deposits(db, dry_run=True)
        # None of the rules should match (not staking token, no interest keywords,
        # below freq threshold, above $50 value threshold)
        assert len(changes) == 0

    def test_small_value_interest_threshold(self, db):
        """3+ small-value deposits totaling under $50 → interest."""
        wallet = create_wallet(db, name="DeFi Vault")
        usdc = create_asset(db, symbol="USDC")
        db.commit()

        for i in range(4):
            create_transaction(
                db,
                datetime_utc=datetime(2025, 2, i + 1, tzinfo=timezone.utc),
                tx_type="deposit",
                to_wallet_id=wallet.id,
                to_asset_id=usdc.id,
                to_amount="0.50",
                to_value_usd="5.00",
                label="crypto_deposit",
            )
        db.commit()

        changes = reclassify_crypto_deposits(db, dry_run=True)
        assert len(changes) == 4
        assert all(c["new_type"] == "interest" for c in changes)
        assert "small-value" in changes[0]["reason"]

    def test_invalid_to_value_usd_skipped(self, db):
        """Invalid to_value_usd doesn't crash (ValueError/TypeError caught)."""
        wallet = create_wallet(db, name="DeFi")
        usdc = create_asset(db, symbol="USDC")
        db.commit()

        for i in range(4):
            create_transaction(
                db,
                datetime_utc=datetime(2025, 3, i + 1, tzinfo=timezone.utc),
                tx_type="deposit",
                to_wallet_id=wallet.id,
                to_asset_id=usdc.id,
                to_amount="0.50",
                to_value_usd="not_a_number" if i == 0 else "5.00",
                label="crypto_deposit",
            )
        db.commit()

        # Should not raise, even with "not_a_number" in to_value_usd
        changes = reclassify_crypto_deposits(db, dry_run=True)
        # 4 deposits, total < $50 (15 + 0 for invalid), count >= 3
        assert len(changes) == 4

    def test_no_to_asset_id_uses_empty_symbol(self, db):
        """Transaction with no to_asset_id gets empty symbol, no crash."""
        wallet = create_wallet(db, name="Unknown")
        db.commit()

        create_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="deposit",
            to_wallet_id=wallet.id,
            to_amount="1.0",
            label="crypto_deposit",
            # No to_asset_id
        )
        db.commit()

        # Should not crash
        changes = reclassify_crypto_deposits(db, dry_run=True)
        # No rules match for empty symbol
        assert len(changes) == 0
