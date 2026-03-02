"""Tests for the account-level sync API endpoints."""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from app.models.account import Account
from app.models.wallet import Wallet


@pytest.fixture
def btc_wallet(db):
    w = Wallet(name="BTC Test", type="hardware", category="wallet")
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


@pytest.fixture
def btc_account(db, btc_wallet):
    a = Account(
        wallet_id=btc_wallet.id,
        name="BTC Account",
        blockchain="bitcoin",
        address="bc1qw508d6qejxtdg4y5r3zarvary0c5xw7kv8f3t4",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@pytest.fixture
def exchange_wallet(db):
    w = Wallet(name="Coinbase", type="exchange", category="exchange")
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


class TestAccountSyncEndpoint:
    def test_sync_success(self, client, btc_wallet, btc_account):
        mock_result = {"imported": 5, "skipped": 2, "errors": 0, "error_messages": []}

        with patch("app.api.accounts.sync_account", new_callable=AsyncMock) as mock_sync:
            mock_sync.return_value = mock_result
            resp = client.post(
                f"/api/wallets/{btc_wallet.id}/accounts/{btc_account.id}/sync"
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["imported"] == 5
        assert data["skipped"] == 2
        assert data["status"] == "completed"

    def test_sync_validation_error(self, client, btc_wallet, btc_account):
        with patch("app.api.accounts.sync_account", new_callable=AsyncMock) as mock_sync:
            mock_sync.side_effect = ValueError("Invalid address: bad format")
            resp = client.post(
                f"/api/wallets/{btc_wallet.id}/accounts/{btc_account.id}/sync"
            )

        assert resp.status_code == 400
        assert "Invalid address" in resp.json()["detail"]

    def test_sync_conflict(self, client, btc_wallet, btc_account):
        with patch("app.api.accounts.sync_account", new_callable=AsyncMock) as mock_sync:
            mock_sync.side_effect = RuntimeError("Sync already in progress")
            resp = client.post(
                f"/api/wallets/{btc_wallet.id}/accounts/{btc_account.id}/sync"
            )

        assert resp.status_code == 409

    def test_sync_account_not_found(self, client, btc_wallet):
        resp = client.post(f"/api/wallets/{btc_wallet.id}/accounts/999/sync")
        assert resp.status_code == 404

    def test_sync_wallet_not_found(self, client):
        resp = client.post("/api/wallets/999/accounts/1/sync")
        assert resp.status_code == 404


class TestAccountSyncStatusEndpoint:
    def test_status_never_synced(self, client, btc_wallet, btc_account):
        resp = client.get(
            f"/api/wallets/{btc_wallet.id}/accounts/{btc_account.id}/sync-status"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["last_synced_at"] is None
        assert data["sync_in_progress"] is False
        assert data["has_address"] is True

    def test_status_after_sync(self, client, db, btc_wallet, btc_account):
        btc_account.last_synced_at = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        db.commit()

        resp = client.get(
            f"/api/wallets/{btc_wallet.id}/accounts/{btc_account.id}/sync-status"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["last_synced_at"] is not None

    def test_status_account_not_found(self, client, btc_wallet):
        resp = client.get(f"/api/wallets/{btc_wallet.id}/accounts/999/sync-status")
        assert resp.status_code == 404
