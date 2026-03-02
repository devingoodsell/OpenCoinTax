"""Integration tests for reports API routes."""


class TestForm8949:
    def test_empty_report(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/reports/8949/2025")
        assert resp.status_code == 200

    def test_csv_export(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/reports/8949/2025/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")


class TestScheduleD:
    def test_empty_report(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/reports/schedule-d/2025")
        assert resp.status_code == 200


class TestTaxSummaryReport:
    def test_empty_report(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/reports/tax-summary/2025")
        assert resp.status_code == 200


class TestTurboTax:
    def test_turbotax_csv(self, client, db, seed_assets, seed_wallets, seed_settings):
        # TurboTax export is not yet implemented, returns JSON placeholder
        resp = client.get("/api/reports/turbotax/2025")
        assert resp.status_code == 200
