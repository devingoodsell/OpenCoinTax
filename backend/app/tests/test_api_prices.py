"""Integration tests for prices API routes."""

from unittest.mock import patch


class TestRefreshCurrent:
    def test_refresh_current(self, client, db, seed_assets, seed_wallets, seed_settings):
        mock_result = {"updated": 0, "failed": 0, "skipped": 0, "mapped": 0}
        with patch("app.api.prices.refresh_current_prices", return_value=mock_result):
            resp = client.post("/api/prices/refresh-current")
            assert resp.status_code == 200


class TestBackfillPrices:
    def test_backfill(self, client, db, seed_assets, seed_wallets, seed_settings):
        mock_result = {"total_stored": 0, "assets_processed": 0, "assets_failed": 0, "assets_skipped": 0, "assets_mapped": 0}
        with patch("app.api.prices.backfill_historical_prices", return_value=mock_result):
            resp = client.post("/api/prices/backfill")
            assert resp.status_code == 200


class TestMissingPrices:
    def test_list_missing(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/prices/missing/2025")
        assert resp.status_code == 200
