"""Tests for staking_handler — staking income calculation."""

from datetime import datetime, timezone
from decimal import Decimal

from app.services.staking_handler import calculate_staking_income
from app.tests.factories import create_asset, create_wallet, create_transaction


class TestCalculateStakingIncome:
    def test_staking_reward_classification(self, db):
        wallet = create_wallet(db, name="Ledger")
        eth = create_asset(db, symbol="ETH")
        db.commit()

        create_transaction(
            db,
            datetime_utc=datetime(2025, 3, 15, tzinfo=timezone.utc),
            tx_type="staking_reward",
            to_wallet_id=wallet.id,
            to_asset_id=eth.id,
            to_amount="0.5",
            to_value_usd="1000.00",
        )
        db.commit()

        result = calculate_staking_income(db, wallet.id, eth.id, 2025)
        assert result["staking_income"] == "1000.00"
        assert result["total_income"] == "1000.00"

    def test_multiple_income_types(self, db):
        wallet = create_wallet(db, name="Coinbase")
        eth = create_asset(db, symbol="ETH")
        db.commit()

        create_transaction(
            db,
            datetime_utc=datetime(2025, 2, 1, tzinfo=timezone.utc),
            tx_type="staking_reward",
            to_wallet_id=wallet.id,
            to_asset_id=eth.id,
            to_amount="0.1",
            to_value_usd="200.00",
        )
        create_transaction(
            db,
            datetime_utc=datetime(2025, 3, 1, tzinfo=timezone.utc),
            tx_type="interest",
            to_wallet_id=wallet.id,
            to_asset_id=eth.id,
            to_amount="0.05",
            to_value_usd="100.00",
        )
        db.commit()

        result = calculate_staking_income(db, wallet.id, eth.id, 2025)
        assert result["staking_income"] == "200.00"
        assert result["interest_income"] == "100.00"
        assert result["total_income"] == "300.00"

    def test_non_staking_not_counted(self, db):
        wallet = create_wallet(db, name="Coinbase")
        btc = create_asset(db, symbol="BTC")
        db.commit()

        # A buy is not income
        create_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id,
            to_asset_id=btc.id,
            to_amount="1.0",
            to_value_usd="50000.00",
        )
        db.commit()

        result = calculate_staking_income(db, wallet.id, btc.id, 2025)
        assert result["total_income"] == "0.00"

    def test_filters_by_tax_year(self, db):
        wallet = create_wallet(db, name="Ledger")
        eth = create_asset(db, symbol="ETH")
        db.commit()

        # 2024 reward — should not count in 2025
        create_transaction(
            db,
            datetime_utc=datetime(2024, 6, 1, tzinfo=timezone.utc),
            tx_type="staking_reward",
            to_wallet_id=wallet.id,
            to_asset_id=eth.id,
            to_amount="1.0",
            to_value_usd="3000.00",
        )
        # 2025 reward
        create_transaction(
            db,
            datetime_utc=datetime(2025, 6, 1, tzinfo=timezone.utc),
            tx_type="staking_reward",
            to_wallet_id=wallet.id,
            to_asset_id=eth.id,
            to_amount="0.5",
            to_value_usd="1500.00",
        )
        db.commit()

        result = calculate_staking_income(db, wallet.id, eth.id, 2025)
        assert result["staking_income"] == "1500.00"

    def test_empty_wallet_returns_zeros(self, db):
        wallet = create_wallet(db, name="Empty")
        btc = create_asset(db, symbol="BTC")
        db.commit()

        result = calculate_staking_income(db, wallet.id, btc.id, 2025)
        assert result["total_income"] == "0.00"
        assert result["staking_income"] == "0.00"
        assert result["airdrop_income"] == "0.00"
        assert result["mining_income"] == "0.00"
        assert result["interest_income"] == "0.00"
