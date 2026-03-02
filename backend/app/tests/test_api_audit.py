"""Integration tests for audit API routes."""


class TestReconciliation:
    def test_reconciliation_empty(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/audit/reconciliation")
        assert resp.status_code == 200


class TestMissingBasis:
    def test_missing_basis_empty(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/audit/missing-basis")
        assert resp.status_code == 200


class TestAuditSummary:
    def test_summary(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/audit/summary")
        assert resp.status_code == 200
