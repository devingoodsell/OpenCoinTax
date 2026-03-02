"""Epic 1 API integration tests — wallet CRUD, transaction CRUD, health check."""

from datetime import datetime, timezone


class TestHealthCheck:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestWalletAPI:
    def test_create_wallet(self, client):
        resp = client.post("/api/wallets", json={
            "name": "Coinbase",
            "type": "exchange",
            "provider": "coinbase",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Coinbase"
        assert data["id"] is not None

    def test_list_wallets(self, client):
        client.post("/api/wallets", json={"name": "W1", "type": "exchange"})
        client.post("/api/wallets", json={"name": "W2", "type": "hardware"})
        resp = client.get("/api/wallets")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_get_wallet(self, client):
        create = client.post("/api/wallets", json={"name": "Ledger", "type": "hardware"})
        wid = create.json()["id"]
        resp = client.get(f"/api/wallets/{wid}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Ledger"
        assert "balances" in resp.json()

    def test_update_wallet(self, client):
        create = client.post("/api/wallets", json={"name": "Old", "type": "exchange"})
        wid = create.json()["id"]
        resp = client.put(f"/api/wallets/{wid}", json={"name": "New"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "New"

    def test_delete_wallet(self, client):
        create = client.post("/api/wallets", json={"name": "ToDelete", "type": "other"})
        wid = create.json()["id"]
        resp = client.delete(f"/api/wallets/{wid}")
        assert resp.status_code == 200
        resp2 = client.get(f"/api/wallets/{wid}")
        assert resp2.status_code == 404

    def test_get_nonexistent_wallet(self, client):
        resp = client.get("/api/wallets/9999")
        assert resp.status_code == 404

    def test_set_cost_basis_method(self, client):
        create = client.post("/api/wallets", json={"name": "CB", "type": "exchange"})
        wid = create.json()["id"]
        resp = client.put(f"/api/wallets/{wid}/cost-basis-method", json={
            "cost_basis_method": "hifo",
            "tax_year": 2025,
        })
        assert resp.status_code == 200


class TestTransactionAPI:
    def _create_wallet_and_asset(self, client):
        w = client.post("/api/wallets", json={"name": "CB", "type": "exchange"})
        wid = w.json()["id"]
        # Assets are created directly in DB via seed — for API tests we just use wallet
        return wid

    def test_create_transaction(self, client):
        wid = self._create_wallet_and_asset(client)
        resp = client.post("/api/transactions", json={
            "datetime_utc": "2025-03-15T12:00:00Z",
            "type": "buy",
            "to_wallet_id": wid,
            "to_amount": "1.0",
            "to_value_usd": "30000.00",
        })
        assert resp.status_code == 201
        assert resp.json()["type"] == "buy"

    def test_list_transactions(self, client):
        wid = self._create_wallet_and_asset(client)
        client.post("/api/transactions", json={
            "datetime_utc": "2025-01-01T00:00:00Z",
            "type": "buy",
            "to_wallet_id": wid,
            "to_amount": "0.5",
        })
        client.post("/api/transactions", json={
            "datetime_utc": "2025-02-01T00:00:00Z",
            "type": "sell",
            "from_wallet_id": wid,
            "from_amount": "0.5",
        })
        resp = client.get("/api/transactions")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2

    def test_filter_by_wallet(self, client):
        w1 = client.post("/api/wallets", json={"name": "A", "type": "exchange"}).json()["id"]
        w2 = client.post("/api/wallets", json={"name": "B", "type": "exchange"}).json()["id"]
        client.post("/api/transactions", json={
            "datetime_utc": "2025-01-01T00:00:00Z",
            "type": "buy", "to_wallet_id": w1, "to_amount": "1",
        })
        client.post("/api/transactions", json={
            "datetime_utc": "2025-01-02T00:00:00Z",
            "type": "buy", "to_wallet_id": w2, "to_amount": "2",
        })
        resp = client.get(f"/api/transactions?wallet_id={w1}")
        assert resp.json()["total"] == 1

    def test_get_transaction_detail(self, client):
        wid = self._create_wallet_and_asset(client)
        create = client.post("/api/transactions", json={
            "datetime_utc": "2025-06-01T00:00:00Z",
            "type": "sell",
            "from_wallet_id": wid,
            "from_amount": "0.1",
        })
        tid = create.json()["id"]
        resp = client.get(f"/api/transactions/{tid}")
        assert resp.status_code == 200
        assert "lot_assignments" in resp.json()

    def test_update_transaction(self, client):
        wid = self._create_wallet_and_asset(client)
        create = client.post("/api/transactions", json={
            "datetime_utc": "2025-01-01T00:00:00Z",
            "type": "buy", "to_wallet_id": wid, "to_amount": "1",
        })
        tid = create.json()["id"]
        resp = client.put(f"/api/transactions/{tid}", json={"label": "staking"})
        assert resp.status_code == 200
        assert resp.json()["label"] == "staking"

    def test_delete_transaction(self, client):
        wid = self._create_wallet_and_asset(client)
        create = client.post("/api/transactions", json={
            "datetime_utc": "2025-01-01T00:00:00Z",
            "type": "buy", "to_wallet_id": wid, "to_amount": "1",
        })
        tid = create.json()["id"]
        resp = client.delete(f"/api/transactions/{tid}")
        assert resp.status_code == 200
        resp2 = client.get(f"/api/transactions/{tid}")
        assert resp2.status_code == 404


class TestSettingsAPI:
    def test_get_empty_settings(self, client):
        resp = client.get("/api/settings")
        assert resp.status_code == 200

    def test_put_and_get_settings(self, client):
        client.put("/api/settings", json={"tax_year": "2025", "base_currency": "USD"})
        resp = client.get("/api/settings")
        data = resp.json()
        assert data["tax_year"] == "2025"
        assert data["base_currency"] == "USD"
