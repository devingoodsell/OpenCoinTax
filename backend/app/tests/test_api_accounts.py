"""Integration tests for accounts API routes."""

# Valid-format addresses for testing
BTC_ADDR = "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
ETH_ADDR = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


class TestAccountCRUD:
    def test_create_account(self, client, db, seed_assets, seed_wallets, seed_settings):
        wallet = seed_wallets["Ledger"]
        resp = client.post(f"/api/wallets/{wallet.id}/accounts", json={
            "name": "BTC Acct",
            "address": BTC_ADDR,
            "blockchain": "bitcoin",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "BTC Acct"
        assert data["blockchain"] == "bitcoin"

    def test_list_accounts(self, client, db, seed_assets, seed_wallets, seed_settings):
        wallet = seed_wallets["Ledger"]
        client.post(f"/api/wallets/{wallet.id}/accounts", json={
            "name": "ETH Acct", "address": ETH_ADDR, "blockchain": "ethereum",
        })
        resp = client.get(f"/api/wallets/{wallet.id}/accounts")
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    def test_update_account(self, client, db, seed_assets, seed_wallets, seed_settings):
        wallet = seed_wallets["Ledger"]
        create = client.post(f"/api/wallets/{wallet.id}/accounts", json={
            "name": "Old Name", "address": ETH_ADDR, "blockchain": "ethereum",
        })
        acct_id = create.json()["id"]

        resp = client.put(f"/api/wallets/{wallet.id}/accounts/{acct_id}", json={
            "name": "New Name",
        })
        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    def test_delete_account(self, client, db, seed_assets, seed_wallets, seed_settings):
        wallet = seed_wallets["Ledger"]
        create = client.post(f"/api/wallets/{wallet.id}/accounts", json={
            "name": "Temp Acct", "address": ETH_ADDR, "blockchain": "ethereum",
        })
        acct_id = create.json()["id"]

        resp = client.delete(f"/api/wallets/{wallet.id}/accounts/{acct_id}")
        assert resp.status_code == 200
