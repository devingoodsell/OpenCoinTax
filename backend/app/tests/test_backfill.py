"""Tests for backfill_koinly_usd_values — repairs existing koinly-imported transactions."""

import pytest
from datetime import datetime, timezone

from app.models import Transaction
from app.services.koinly_import import backfill_koinly_usd_values


def _make_tx(db, *, tx_type, source="koinly_import", net_value_usd=None,
             from_value_usd=None, to_value_usd=None, **kwargs):
    tx = Transaction(
        datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
        type=tx_type,
        source=source,
        net_value_usd=net_value_usd,
        from_value_usd=from_value_usd,
        to_value_usd=to_value_usd,
        **kwargs,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


class TestBackfillKoinlyUsdValues:
    def test_backfills_buy_transactions(self, db, seed_assets):
        """Koinly buy with net_value_usd gets to_value_usd backfilled."""
        tx = _make_tx(db, tx_type="buy", net_value_usd="30000.00")
        assert tx.to_value_usd is None

        updated = backfill_koinly_usd_values(db)
        db.flush()

        db.refresh(tx)
        assert tx.to_value_usd == "30000.00"
        assert tx.from_value_usd is None
        assert updated == 1

    def test_backfills_sell_transactions(self, db, seed_assets):
        """Koinly sell with net_value_usd gets from_value_usd backfilled."""
        tx = _make_tx(db, tx_type="sell", net_value_usd="40000.00")
        assert tx.from_value_usd is None

        updated = backfill_koinly_usd_values(db)
        db.flush()

        db.refresh(tx)
        assert tx.from_value_usd == "40000.00"
        assert tx.to_value_usd is None
        assert updated == 1

    def test_backfills_transfer_both_sides(self, db, seed_assets):
        """Koinly transfer gets both from_value_usd and to_value_usd."""
        tx = _make_tx(db, tx_type="transfer", net_value_usd="25000.00")

        updated = backfill_koinly_usd_values(db)
        db.flush()

        db.refresh(tx)
        assert tx.from_value_usd == "25000.00"
        assert tx.to_value_usd == "25000.00"
        assert updated == 1

    def test_backfills_deposit(self, db, seed_assets):
        """Koinly deposit gets to_value_usd backfilled."""
        tx = _make_tx(db, tx_type="deposit", net_value_usd="5000.00")

        updated = backfill_koinly_usd_values(db)
        db.flush()

        db.refresh(tx)
        assert tx.to_value_usd == "5000.00"
        assert updated == 1

    def test_skips_non_koinly(self, db, seed_assets):
        """csv_import source not touched."""
        tx = _make_tx(db, tx_type="buy", source="csv_import", net_value_usd="1000.00")

        updated = backfill_koinly_usd_values(db)
        db.flush()

        db.refresh(tx)
        assert tx.to_value_usd is None
        assert updated == 0

    def test_no_overwrite_existing(self, db, seed_assets):
        """Existing to_value_usd is preserved (not overwritten)."""
        tx = _make_tx(
            db, tx_type="buy",
            net_value_usd="30000.00",
            to_value_usd="29500.00",  # already set
        )

        updated = backfill_koinly_usd_values(db)
        db.flush()

        db.refresh(tx)
        assert tx.to_value_usd == "29500.00"  # not changed
        assert updated == 0

    def test_no_net_value_skipped(self, db, seed_assets):
        """Transaction with no net_value_usd is skipped."""
        tx = _make_tx(db, tx_type="buy", net_value_usd=None)

        updated = backfill_koinly_usd_values(db)
        db.flush()

        db.refresh(tx)
        assert tx.to_value_usd is None
        assert updated == 0

    def test_multiple_transactions(self, db, seed_assets):
        """Multiple transactions are backfilled in one call."""
        _make_tx(db, tx_type="buy", net_value_usd="10000.00")
        _make_tx(db, tx_type="sell", net_value_usd="15000.00")
        _make_tx(db, tx_type="deposit", net_value_usd="5000.00")

        updated = backfill_koinly_usd_values(db)
        assert updated == 3
