"""Integration tests for admin API routes."""

from app.models import Transaction


class TestResetDatabase:
    def test_reset_database(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.post("/api/admin/reset-database")
        assert resp.status_code == 200

    def test_clear_transactions(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.post("/api/admin/clear-transactions")
        assert resp.status_code == 200
        assert db.query(Transaction).count() == 0
