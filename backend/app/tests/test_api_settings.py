"""Integration tests for settings API routes."""


class TestSettings:
    def test_get_settings(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert "default_cost_basis_method" in data

    def test_update_settings(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.put("/api/settings", json={"default_cost_basis_method": "lifo"})
        assert resp.status_code == 200

        # Verify it was updated
        get_resp = client.get("/api/settings")
        assert get_resp.json()["default_cost_basis_method"] == "lifo"
