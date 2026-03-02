"""Integration tests for wallet API routes."""

from app.models import Wallet


class TestWalletCRUD:
    def test_create_wallet(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.post("/api/wallets", json={
            "name": "New Wallet", "type": "exchange",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "New Wallet"
        assert data["type"] == "exchange"
        assert data["id"] is not None

    def test_list_wallets(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/wallets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_get_wallet(self, client, db, seed_assets, seed_wallets, seed_settings):
        wallet = seed_wallets["Coinbase"]
        resp = client.get(f"/api/wallets/{wallet.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Coinbase"

    def test_get_wallet_not_found(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/wallets/99999")
        assert resp.status_code == 404

    def test_update_wallet(self, client, db, seed_assets, seed_wallets, seed_settings):
        wallet = seed_wallets["Coinbase"]
        resp = client.put(f"/api/wallets/{wallet.id}", json={"name": "Updated Coinbase"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Coinbase"

    def test_delete_wallet(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.post("/api/wallets", json={
            "name": "Disposable", "type": "exchange",
        })
        wid = resp.json()["id"]

        resp = client.delete(f"/api/wallets/{wid}")
        assert resp.status_code == 200
        assert db.query(Wallet).filter_by(id=wid).first() is None


class TestCostBasisMethod:
    def test_set_cost_basis_method(self, client, db, seed_assets, seed_wallets, seed_settings):
        wallet = seed_wallets["Coinbase"]
        resp = client.put(f"/api/wallets/{wallet.id}/cost-basis-method", json={
            "cost_basis_method": "lifo", "tax_year": 2025,
        })
        assert resp.status_code == 200
