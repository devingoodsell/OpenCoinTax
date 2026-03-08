"""Tests for API key management utilities and settings API masking."""

import os
from unittest.mock import patch

from app.models import Setting
from app.services.api_keys import (
    API_KEY_SETTINGS,
    get_api_key,
    is_api_key,
    is_masked_value,
    mask_api_key,
)


class TestIsApiKey:
    def test_recognized_keys(self):
        assert is_api_key("etherscan_api_key") is True
        assert is_api_key("helius_api_key") is True
        assert is_api_key("coingecko_api_key") is True
        assert is_api_key("coincap_api_key") is True

    def test_non_api_key(self):
        assert is_api_key("default_cost_basis_method") is False
        assert is_api_key("base_currency") is False
        assert is_api_key("") is False


class TestMaskApiKey:
    def test_normal_key(self):
        result = mask_api_key("sk-abcdef123456")
        assert result == "sk-a\u2022\u2022\u2022\u20223456"

    def test_short_key(self):
        assert mask_api_key("abc") == "\u2022\u2022\u2022"
        assert mask_api_key("abcd") == "\u2022\u2022\u2022\u2022"

    def test_exactly_five_chars(self):
        result = mask_api_key("abcde")
        assert result == "abcd\u2022\u2022\u2022\u2022bcde"

    def test_empty_key(self):
        assert mask_api_key("") == ""

    def test_eight_char_key(self):
        result = mask_api_key("12345678")
        assert result == "1234\u2022\u2022\u2022\u20225678"


class TestIsMaskedValue:
    def test_masked_value(self):
        assert is_masked_value("sk-a\u2022\u2022\u2022\u20223456") is True

    def test_all_bullets(self):
        assert is_masked_value("\u2022\u2022\u2022") is True

    def test_plain_value(self):
        assert is_masked_value("sk-abcdef123456") is False

    def test_empty(self):
        assert is_masked_value("") is False


class TestGetApiKey:
    def test_db_value_takes_priority(self, db):
        db.add(Setting(key="etherscan_api_key", value="db-key-123"))
        db.commit()
        with patch.dict(os.environ, {"CRYPTO_TAX_ETHERSCAN_API_KEY": "env-key-456"}):
            result = get_api_key(db, "etherscan_api_key")
        assert result == "db-key-123"

    def test_falls_back_to_env_var(self, db):
        with patch.dict(os.environ, {"CRYPTO_TAX_HELIUS_API_KEY": "env-key-789"}):
            result = get_api_key(db, "helius_api_key")
        assert result == "env-key-789"

    def test_returns_none_when_not_set(self, db):
        with patch.dict(os.environ, {}, clear=True):
            result = get_api_key(db, "coingecko_api_key")
        assert result is None

    def test_unrecognized_key_returns_none(self, db):
        result = get_api_key(db, "unknown_key")
        assert result is None

    def test_empty_db_value_falls_through(self, db):
        db.add(Setting(key="etherscan_api_key", value=""))
        db.commit()
        with patch.dict(os.environ, {"CRYPTO_TAX_ETHERSCAN_API_KEY": "env-fallback"}):
            result = get_api_key(db, "etherscan_api_key")
        assert result == "env-fallback"


class TestSettingsApiMasking:
    def test_get_masks_api_keys(self, client, db, seed_settings):
        db.add(Setting(key="etherscan_api_key", value="my-secret-key-12345"))
        db.commit()

        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["etherscan_api_key"] != "my-secret-key-12345"
        assert "\u2022" in data["etherscan_api_key"]

    def test_get_does_not_mask_normal_settings(self, client, db, seed_settings):
        resp = client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["default_cost_basis_method"] == "fifo"

    def test_put_skips_masked_api_key(self, client, db, seed_settings):
        db.add(Setting(key="etherscan_api_key", value="original-secret"))
        db.commit()

        # Send back the masked value — should NOT overwrite
        masked = "orig\u2022\u2022\u2022\u2022cret"
        client.put("/api/settings", json={"etherscan_api_key": masked})

        row = db.get(Setting, "etherscan_api_key")
        assert row.value == "original-secret"

    def test_put_updates_real_api_key(self, client, db, seed_settings):
        client.put("/api/settings", json={"etherscan_api_key": "new-real-key-value"})

        row = db.get(Setting, "etherscan_api_key")
        assert row.value == "new-real-key-value"

    def test_put_clears_api_key_with_empty_string(self, client, db, seed_settings):
        db.add(Setting(key="etherscan_api_key", value="old-key"))
        db.commit()

        client.put("/api/settings", json={"etherscan_api_key": ""})

        row = db.get(Setting, "etherscan_api_key")
        assert row.value == ""


class TestPriceEndpointWarnings:
    def test_refresh_current_returns_warnings(self, client, db, seed_assets, seed_wallets, seed_settings):
        mock_result = {
            "updated": 0, "failed": 0, "skipped": 0, "mapped": 0,
            "warnings": ["No price data available for: UNKNOWN (missing CoinGecko mapping)"],
        }
        with patch("app.api.prices.refresh_current_prices", return_value=mock_result):
            resp = client.post("/api/prices/refresh-current")
            assert resp.status_code == 200
            data = resp.json()
            assert "warnings" in data
            assert len(data["warnings"]) == 1
            assert "UNKNOWN" in data["warnings"][0]

    def test_backfill_returns_running_status(self, client, db, seed_assets, seed_wallets, seed_settings):
        import time
        import app.api.prices as prices_mod
        # Reset backfill state to idle
        prices_mod._backfill_status = {"status": "idle", "result": None, "error": None}
        mock_result = {
            "total_stored": 0, "assets_processed": 0, "assets_failed": 0,
            "assets_skipped": 0, "assets_mapped": 0,
            "warnings": ["No price data available for: FOO, BAR (missing CoinGecko mapping)"],
        }
        with patch("app.api.prices.backfill_historical_prices", return_value=mock_result):
            resp = client.post("/api/prices/backfill")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] in ("running", "completed")
            # Wait briefly for background thread to complete with mock
            time.sleep(0.3)
            status_resp = client.get("/api/prices/backfill/status")
            assert status_resp.status_code == 200
            status_data = status_resp.json()
            assert status_data["status"] == "completed"
            assert len(status_data["result"]["warnings"]) == 1
        # Reset state after test
        prices_mod._backfill_status = {"status": "idle", "result": None, "error": None}

    def test_refresh_current_empty_warnings(self, client, db, seed_assets, seed_wallets, seed_settings):
        mock_result = {"updated": 0, "failed": 0, "skipped": 0, "mapped": 0, "warnings": []}
        with patch("app.api.prices.refresh_current_prices", return_value=mock_result):
            resp = client.post("/api/prices/refresh-current")
            assert resp.status_code == 200
            assert resp.json()["warnings"] == []
