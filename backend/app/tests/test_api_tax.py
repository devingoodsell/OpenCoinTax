"""Integration tests for tax API routes."""


class TestTaxRecalculate:
    def test_recalculate(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.post("/api/tax/recalculate")
        assert resp.status_code == 200

    def test_recalculate_with_year(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.post("/api/tax/recalculate", json={"year": 2025})
        assert resp.status_code == 200


class TestTaxSummary:
    def test_summary_empty(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/tax/summary/2025")
        assert resp.status_code == 200


class TestTaxGains:
    def test_gains_empty(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/tax/gains/2025")
        assert resp.status_code == 200


class TestTaxLots:
    def test_list_lots(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/tax/lots")
        assert resp.status_code == 200


class TestTaxValidate:
    def test_validate(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.post("/api/tax/validate")
        assert resp.status_code == 200


class TestCompareMethods:
    def test_compare_methods(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/tax/compare-methods/2025")
        assert resp.status_code == 200


class TestWhatIf:
    def test_whatif_not_found(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/tax/whatif/99999")
        assert resp.status_code in (400, 404, 422)


class TestReclassifyDeposits:
    def test_reclassify(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.post("/api/tax/reclassify-deposits?dry_run=true")
        assert resp.status_code == 200
