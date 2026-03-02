"""Integration tests for transaction API routes."""

from datetime import datetime, timezone

from app.models import Transaction
from app.tests.conftest import make_transaction


class TestTransactionCRUD:
    def test_create_transaction(self, client, db, seed_assets, seed_wallets, seed_settings):
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        resp = client.post("/api/transactions", json={
            "datetime_utc": "2025-01-15T10:00:00Z",
            "type": "buy",
            "to_wallet_id": wallet.id,
            "to_asset_id": btc.id,
            "to_amount": "1.0",
            "to_value_usd": "50000.00",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["type"] == "buy"

    def test_list_transactions(self, client, db, seed_assets, seed_wallets, seed_settings):
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        make_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id, to_asset_id=btc.id,
            to_amount="1.0", to_value_usd="50000",
        )

        resp = client.get("/api/transactions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1

    def test_list_transactions_pagination(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/transactions?page=1&page_size=5")
        assert resp.status_code == 200

    def test_get_transaction(self, client, db, seed_assets, seed_wallets, seed_settings):
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        tx = make_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id, to_asset_id=btc.id,
            to_amount="0.5",
        )

        resp = client.get(f"/api/transactions/{tx.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == tx.id

    def test_get_transaction_not_found(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/transactions/99999")
        assert resp.status_code == 404

    def test_update_transaction(self, client, db, seed_assets, seed_wallets, seed_settings):
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        tx = make_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id, to_asset_id=btc.id,
            to_amount="1.0",
        )

        resp = client.put(f"/api/transactions/{tx.id}", json={
            "to_amount": "2.0",
        })
        assert resp.status_code == 200

    def test_delete_transaction(self, client, db, seed_assets, seed_wallets, seed_settings):
        wallet = seed_wallets["Coinbase"]
        btc = seed_assets["BTC"]
        tx = make_transaction(
            db,
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            tx_type="buy",
            to_wallet_id=wallet.id, to_asset_id=btc.id,
            to_amount="0.1",
        )

        resp = client.delete(f"/api/transactions/{tx.id}")
        assert resp.status_code == 200
        assert db.query(Transaction).filter_by(id=tx.id).first() is None

    def test_error_count(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/transactions/error-count")
        assert resp.status_code == 200
        assert "error_count" in resp.json()
