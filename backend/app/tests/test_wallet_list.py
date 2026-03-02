"""Tests for wallet list enhancements: search, sort, archive, enriched response."""
import pytest


def _create_wallet(client, name="Ledger", wallet_type="hardware"):
    resp = client.post("/api/wallets", json={"name": name, "type": wallet_type})
    assert resp.status_code == 201
    return resp.json()


class TestWalletCreate:
    def test_create_wallet_derives_category_wallet(self, client):
        w = _create_wallet(client, name="Ledger", wallet_type="hardware")
        assert w["category"] == "wallet"
        assert w["is_archived"] is False

    def test_create_wallet_derives_category_exchange(self, client):
        w = _create_wallet(client, name="Coinbase", wallet_type="exchange")
        assert w["category"] == "exchange"

    def test_create_software_wallet(self, client):
        w = _create_wallet(client, name="MetaMask", wallet_type="software")
        assert w["category"] == "wallet"

    def test_wallet_response_no_address_fields(self, client):
        w = _create_wallet(client)
        assert "address" not in w
        assert "blockchain" not in w
        assert "last_synced_at" not in w
        assert "koinly_wallet_id" not in w


class TestWalletListSearch:
    def test_search_by_name(self, client):
        _create_wallet(client, name="Coinbase", wallet_type="exchange")
        _create_wallet(client, name="Coinbase Pro", wallet_type="exchange")
        _create_wallet(client, name="Ledger", wallet_type="hardware")

        resp = client.get("/api/wallets?search=coin")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 2
        names = {r["name"] for r in results}
        assert names == {"Coinbase", "Coinbase Pro"}

    def test_search_empty_returns_all(self, client):
        _create_wallet(client, name="A")
        _create_wallet(client, name="B")
        resp = client.get("/api/wallets")
        assert len(resp.json()) == 2


class TestWalletListSort:
    def test_sort_by_name_asc(self, client):
        _create_wallet(client, name="Zebra")
        _create_wallet(client, name="Alpha")
        resp = client.get("/api/wallets?sort_by=name&sort_dir=asc")
        names = [w["name"] for w in resp.json()]
        assert names == ["Alpha", "Zebra"]

    def test_sort_by_name_desc(self, client):
        _create_wallet(client, name="Alpha")
        _create_wallet(client, name="Zebra")
        resp = client.get("/api/wallets?sort_by=name&sort_dir=desc")
        names = [w["name"] for w in resp.json()]
        assert names == ["Zebra", "Alpha"]


class TestWalletListArchive:
    def test_default_excludes_archived(self, client):
        w = _create_wallet(client)
        client.put(f"/api/wallets/{w['id']}", json={"is_archived": True})
        resp = client.get("/api/wallets")
        assert len(resp.json()) == 0

    def test_include_archived(self, client):
        w = _create_wallet(client)
        client.put(f"/api/wallets/{w['id']}", json={"is_archived": True})
        resp = client.get("/api/wallets?include_archived=true")
        assert len(resp.json()) == 1


class TestWalletListEnriched:
    def test_list_has_account_count(self, client):
        w = _create_wallet(client)
        client.post(
            f"/api/wallets/{w['id']}/accounts",
            json={"name": "BTC", "address": "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4", "blockchain": "bitcoin"},
        )
        resp = client.get("/api/wallets")
        assert resp.json()[0]["account_count"] == 1

    def test_exchange_has_zero_account_count(self, client):
        _create_wallet(client, name="Coinbase", wallet_type="exchange")
        resp = client.get("/api/wallets")
        assert resp.json()[0]["account_count"] == 0

    def test_list_has_transaction_count(self, client):
        w = _create_wallet(client)
        resp = client.get("/api/wallets")
        assert resp.json()[0]["transaction_count"] == 0

    def test_list_has_total_value_usd(self, client):
        w = _create_wallet(client)
        resp = client.get("/api/wallets")
        assert resp.json()[0]["total_value_usd"] == "0.00"


class TestWalletDetail:
    def test_detail_has_transaction_summary(self, client):
        w = _create_wallet(client)
        resp = client.get(f"/api/wallets/{w['id']}")
        assert resp.status_code == 200
        summary = resp.json()["transaction_summary"]
        assert summary["total"] == 0
        assert "deposits" in summary
        assert "withdrawals" in summary

    def test_detail_has_accounts_for_wallet(self, client):
        w = _create_wallet(client)
        client.post(
            f"/api/wallets/{w['id']}/accounts",
            json={"name": "BTC", "address": "bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4", "blockchain": "bitcoin"},
        )
        resp = client.get(f"/api/wallets/{w['id']}")
        assert len(resp.json()["accounts"]) == 1

    def test_detail_exchange_has_no_accounts(self, client):
        w = _create_wallet(client, name="Coinbase", wallet_type="exchange")
        resp = client.get(f"/api/wallets/{w['id']}")
        assert resp.json()["accounts"] == []

    def test_detail_has_exchange_connection_status(self, client):
        w = _create_wallet(client, name="Coinbase", wallet_type="exchange")
        resp = client.get(f"/api/wallets/{w['id']}")
        data = resp.json()
        assert data["has_exchange_connection"] is False
        assert data["exchange_last_synced_at"] is None

    def test_update_notes(self, client):
        w = _create_wallet(client)
        client.put(f"/api/wallets/{w['id']}", json={"notes": "Primary trading"})
        resp = client.get(f"/api/wallets/{w['id']}")
        assert resp.json()["notes"] == "Primary trading"

    def test_archive_wallet(self, client):
        w = _create_wallet(client)
        resp = client.put(f"/api/wallets/{w['id']}", json={"is_archived": True})
        assert resp.json()["is_archived"] is True

    def test_detail_balance_field_names(self, client, db, seed_assets, seed_settings):
        """API response balances use symbol, cost_basis_usd, quantity, asset_id."""
        from app.models import TaxLot, Transaction
        from datetime import datetime, timezone

        w = _create_wallet(client)
        wallet_id = w["id"]
        btc = seed_assets["BTC"]

        # Create a dummy transaction for the FK reference
        tx = Transaction(
            datetime_utc=datetime(2025, 1, 1, tzinfo=timezone.utc),
            type="buy",
            to_wallet_id=wallet_id,
            to_asset_id=btc.id,
            to_amount="1.5",
            to_value_usd="45000.00",
            source="manual",
        )
        db.add(tx)
        db.flush()

        # Create a tax lot directly to simulate calculated data
        lot = TaxLot(
            wallet_id=wallet_id,
            asset_id=btc.id,
            amount="1.5",
            remaining_amount="1.5",
            cost_basis_usd="45000.00",
            cost_basis_per_unit="30000.00000000",
            acquired_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            acquisition_tx_id=tx.id,
            source_type="purchase",
        )
        db.add(lot)
        db.commit()

        resp = client.get(f"/api/wallets/{wallet_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["balances"]) == 1

        balance = data["balances"][0]
        assert "symbol" in balance
        assert "cost_basis_usd" in balance
        assert "quantity" in balance
        assert "asset_id" in balance
        assert balance["symbol"] == "BTC"
        assert balance["asset_id"] == btc.id
        # Verify the old field names are NOT present
        assert "asset_symbol" not in balance
        assert "value_usd" not in balance
