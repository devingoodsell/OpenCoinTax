"""Tests for account CRUD API endpoints."""
import pytest


def _create_wallet(client, name="Ledger", wallet_type="hardware"):
    resp = client.post("/api/wallets", json={"name": name, "type": wallet_type})
    assert resp.status_code == 201
    return resp.json()


class TestCreateAccount:
    def test_create_account_success(self, client):
        wallet = _create_wallet(client)
        resp = client.post(
            f"/api/wallets/{wallet['id']}/accounts",
            json={"name": "My BTC", "address": "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4", "blockchain": "bitcoin"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My BTC"
        assert data["address"] == "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"
        assert data["blockchain"] == "bitcoin"
        assert data["wallet_id"] == wallet["id"]
        assert data["is_archived"] is False
        assert data["last_synced_at"] is None

    def test_create_account_for_exchange_fails(self, client):
        wallet = _create_wallet(client, name="Coinbase", wallet_type="exchange")
        resp = client.post(
            f"/api/wallets/{wallet['id']}/accounts",
            json={"name": "BTC", "address": "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4", "blockchain": "bitcoin"},
        )
        assert resp.status_code == 400
        assert "exchanges" in resp.json()["detail"].lower()

    def test_create_account_invalid_address(self, client):
        wallet = _create_wallet(client)
        resp = client.post(
            f"/api/wallets/{wallet['id']}/accounts",
            json={"name": "Bad Addr", "address": "not_valid", "blockchain": "bitcoin"},
        )
        assert resp.status_code == 400
        assert "invalid" in resp.json()["detail"].lower()

    def test_create_account_wallet_not_found(self, client):
        resp = client.post(
            "/api/wallets/999/accounts",
            json={"name": "BTC", "address": "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4", "blockchain": "bitcoin"},
        )
        assert resp.status_code == 404


class TestListAccounts:
    def test_list_accounts(self, client):
        wallet = _create_wallet(client)
        client.post(
            f"/api/wallets/{wallet['id']}/accounts",
            json={"name": "BTC 1", "address": "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4", "blockchain": "bitcoin"},
        )
        client.post(
            f"/api/wallets/{wallet['id']}/accounts",
            json={"name": "ETH 1", "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD1e", "blockchain": "ethereum"},
        )
        resp = client.get(f"/api/wallets/{wallet['id']}/accounts")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_excludes_archived_by_default(self, client):
        wallet = _create_wallet(client)
        resp1 = client.post(
            f"/api/wallets/{wallet['id']}/accounts",
            json={"name": "BTC 1", "address": "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4", "blockchain": "bitcoin"},
        )
        acct_id = resp1.json()["id"]
        client.put(f"/api/wallets/{wallet['id']}/accounts/{acct_id}", json={"is_archived": True})

        resp = client.get(f"/api/wallets/{wallet['id']}/accounts")
        assert len(resp.json()) == 0

    def test_list_includes_archived_when_requested(self, client):
        wallet = _create_wallet(client)
        resp1 = client.post(
            f"/api/wallets/{wallet['id']}/accounts",
            json={"name": "BTC 1", "address": "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4", "blockchain": "bitcoin"},
        )
        acct_id = resp1.json()["id"]
        client.put(f"/api/wallets/{wallet['id']}/accounts/{acct_id}", json={"is_archived": True})

        resp = client.get(f"/api/wallets/{wallet['id']}/accounts?include_archived=true")
        assert len(resp.json()) == 1


class TestUpdateAccount:
    def test_rename_account(self, client):
        wallet = _create_wallet(client)
        acct = client.post(
            f"/api/wallets/{wallet['id']}/accounts",
            json={"name": "BTC 1", "address": "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4", "blockchain": "bitcoin"},
        ).json()

        resp = client.put(
            f"/api/wallets/{wallet['id']}/accounts/{acct['id']}",
            json={"name": "My BTC Savings"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "My BTC Savings"

    def test_archive_account(self, client):
        wallet = _create_wallet(client)
        acct = client.post(
            f"/api/wallets/{wallet['id']}/accounts",
            json={"name": "BTC 1", "address": "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4", "blockchain": "bitcoin"},
        ).json()

        resp = client.put(
            f"/api/wallets/{wallet['id']}/accounts/{acct['id']}",
            json={"is_archived": True},
        )
        assert resp.status_code == 200
        assert resp.json()["is_archived"] is True

    def test_cannot_change_address(self, client):
        wallet = _create_wallet(client)
        acct = client.post(
            f"/api/wallets/{wallet['id']}/accounts",
            json={"name": "BTC 1", "address": "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4", "blockchain": "bitcoin"},
        ).json()

        resp = client.put(
            f"/api/wallets/{wallet['id']}/accounts/{acct['id']}",
            json={"name": "Renamed"},
        )
        assert resp.status_code == 200
        assert resp.json()["address"] == "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4"

    def test_update_not_found(self, client):
        wallet = _create_wallet(client)
        resp = client.put(
            f"/api/wallets/{wallet['id']}/accounts/999",
            json={"name": "Test"},
        )
        assert resp.status_code == 404


class TestDeleteAccount:
    def test_delete_account(self, client):
        wallet = _create_wallet(client)
        acct = client.post(
            f"/api/wallets/{wallet['id']}/accounts",
            json={"name": "BTC 1", "address": "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4", "blockchain": "bitcoin"},
        ).json()

        resp = client.delete(f"/api/wallets/{wallet['id']}/accounts/{acct['id']}")
        assert resp.status_code == 200

        resp = client.get(f"/api/wallets/{wallet['id']}/accounts")
        assert len(resp.json()) == 0

    def test_delete_not_found(self, client):
        wallet = _create_wallet(client)
        resp = client.delete(f"/api/wallets/{wallet['id']}/accounts/999")
        assert resp.status_code == 404
