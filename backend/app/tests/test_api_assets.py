"""Integration tests for assets API routes."""


class TestHideAsset:
    def test_hide_and_unhide(self, client, db, seed_assets, seed_wallets, seed_settings):
        btc = seed_assets["BTC"]

        # Hide
        resp = client.patch(f"/api/assets/{btc.id}/hide")
        assert resp.status_code == 200

        # Check hidden list
        hidden = client.get("/api/assets/hidden")
        assert hidden.status_code == 200
        hidden_ids = [a["id"] for a in hidden.json()]
        assert btc.id in hidden_ids

        # Unhide
        resp = client.patch(f"/api/assets/{btc.id}/unhide")
        assert resp.status_code == 200

    def test_list_hidden_empty(self, client, db, seed_assets, seed_wallets, seed_settings):
        resp = client.get("/api/assets/hidden")
        assert resp.status_code == 200
        assert resp.json() == []
