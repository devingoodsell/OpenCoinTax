"""Tests for CoinCap v3 integration.

Covers:
- SYMBOL_TO_COINCAP mapping
- backfill_old_prices() with mocked HTTP
- Skipping assets with existing DB coverage
- Missing API key handling
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.price_history import PriceHistory
from app.services import coincap as coincap_mod
from app.services.coincap import SYMBOL_TO_COINCAP, backfill_old_prices, fetch_price_range
from app.services.price_service import PriceService
from app.tests.conftest import make_transaction


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def btc(seed_assets) -> Asset:
    return seed_assets["BTC"]


@pytest.fixture
def eth(seed_assets) -> Asset:
    return seed_assets["ETH"]


@pytest.fixture
def wallets(db, seed_wallets):
    return seed_wallets


# ======================================================================
# SYMBOL_TO_COINCAP mapping tests
# ======================================================================


class TestSymbolMapping:
    """Test that the symbol mapping covers key assets."""

    def test_covers_major_coins(self):
        for symbol in ("BTC", "ETH", "SOL", "ADA", "DOT", "LINK", "AVAX"):
            assert symbol in SYMBOL_TO_COINCAP, f"{symbol} missing from SYMBOL_TO_COINCAP"

    def test_btc_maps_to_bitcoin(self):
        assert SYMBOL_TO_COINCAP["BTC"] == "bitcoin"

    def test_eth_maps_to_ethereum(self):
        assert SYMBOL_TO_COINCAP["ETH"] == "ethereum"

    def test_no_empty_values(self):
        for symbol, slug in SYMBOL_TO_COINCAP.items():
            assert slug, f"{symbol} has empty slug"
            assert isinstance(slug, str)


# ======================================================================
# fetch_price_range tests (mocked HTTP)
# ======================================================================


class TestFetchPriceRange:
    """Test the CoinCap fetch_price_range function with mocked HTTP."""

    def test_successful_fetch(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": [
                {"priceUsd": "65000.123", "time": 1609459200000},  # 2021-01-01
                {"priceUsd": "66000.456", "time": 1609545600000},  # 2021-01-02
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch("app.services.coincap.httpx.Client", return_value=mock_client):
            result = fetch_price_range(
                "bitcoin",
                date(2021, 1, 1),
                date(2021, 1, 2),
                {"Authorization": "Bearer test-key"},
            )

        assert result is not None
        assert len(result) == 2
        mock_client.get.assert_called_once()

    def test_401_returns_none(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 401

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch("app.services.coincap.httpx.Client", return_value=mock_client):
            result = fetch_price_range(
                "bitcoin", date(2021, 1, 1), date(2021, 1, 2),
                {"Authorization": "Bearer bad-key"},
            )

        assert result is None

    def test_timeout_returns_none(self):
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.TimeoutException("timed out")

        with patch("app.services.coincap.httpx.Client", return_value=mock_client):
            result = fetch_price_range(
                "bitcoin", date(2021, 1, 1), date(2021, 1, 2),
                {"Authorization": "Bearer test-key"},
            )

        assert result is None


# ======================================================================
# backfill_old_prices tests
# ======================================================================


class TestBackfillOldPrices:
    """Test backfill_old_prices with mocked HTTP and DB."""

    def test_no_api_key_returns_warning(self, db, seed_assets):
        """Without a CoinCap API key, should return early with a warning."""
        with patch("app.services.coincap.get_api_key", return_value=None):
            result = backfill_old_prices(db)

        assert result["total_stored"] == 0
        assert len(result["warnings"]) == 1
        assert "CoinCap API key" in result["warnings"][0]

    def test_backfills_old_missing_prices(self, db, seed_assets, wallets):
        """Should fetch old prices and store them."""
        btc = seed_assets["BTC"]
        # Set up coincap_id on the asset
        btc.coincap_id = "bitcoin"
        db.commit()

        # Create a transaction with a date >365 days ago
        old_date = datetime(2023, 6, 15, 10, 0, 0)
        make_transaction(
            db,
            datetime_utc=old_date,
            tx_type="buy",
            to_wallet_id=wallets["Coinbase"].id,
            to_amount="1.0",
            to_asset_id=btc.id,
            from_amount="25000",
            from_asset_id=seed_assets["USD"].id,
        )

        mock_prices = {date(2023, 6, 15): Decimal("25000.50")}

        with patch("app.services.coincap.get_api_key", return_value="test-key"), \
             patch("app.services.coincap.fetch_price_range", return_value=mock_prices), \
             patch("app.services.coincap.auto_map_coincap_ids", return_value=0), \
             patch("app.services.coincap.time.sleep"):
            result = backfill_old_prices(db)

        assert result["total_stored"] == 1
        assert result["assets_processed"] == 1

        # Verify stored in DB
        stored = (
            db.query(PriceHistory)
            .filter_by(asset_id=btc.id, date=date(2023, 6, 15), source="coincap")
            .first()
        )
        assert stored is not None

    def test_skips_assets_without_coincap_id(self, db, seed_assets, wallets):
        """Assets without coincap_id should be skipped."""
        # Create an asset without coincap_id
        no_cc = Asset(symbol="NOCC", name="No CoinCap", is_fiat=False, coingecko_id=None, coincap_id=None)
        db.add(no_cc)
        db.commit()
        db.refresh(no_cc)

        old_date = datetime(2023, 1, 1, 10, 0, 0)
        make_transaction(
            db,
            datetime_utc=old_date,
            tx_type="buy",
            to_wallet_id=wallets["Coinbase"].id,
            to_amount="100",
            to_asset_id=no_cc.id,
            from_amount="1000",
            from_asset_id=seed_assets["USD"].id,
        )

        with patch("app.services.coincap.get_api_key", return_value="test-key"), \
             patch("app.services.coincap.auto_map_coincap_ids", return_value=0), \
             patch("app.services.coincap.time.sleep"):
            result = backfill_old_prices(db)

        assert result["total_stored"] == 0
        assert result["assets_skipped"] >= 1

    def test_skips_already_covered_dates(self, db, seed_assets, wallets):
        """Dates that already have prices in DB should not be re-fetched."""
        btc = seed_assets["BTC"]
        btc.coincap_id = "bitcoin"
        db.commit()

        old_date = datetime(2023, 3, 1, 10, 0, 0)
        make_transaction(
            db,
            datetime_utc=old_date,
            tx_type="buy",
            to_wallet_id=wallets["Coinbase"].id,
            to_amount="0.5",
            to_asset_id=btc.id,
            from_amount="15000",
            from_asset_id=seed_assets["USD"].id,
        )

        # Pre-populate a price for this date
        db.add(PriceHistory(
            asset_id=btc.id, date=date(2023, 3, 1),
            price_usd="30000.00000000", source="coingecko",
        ))
        db.commit()

        with patch("app.services.coincap.get_api_key", return_value="test-key"), \
             patch("app.services.coincap.auto_map_coincap_ids", return_value=0), \
             patch("app.services.coincap.fetch_price_range") as mock_fetch, \
             patch("app.services.coincap.time.sleep"):
            result = backfill_old_prices(db)

        # Should not have called the API at all since no dates are missing
        assert result["total_stored"] == 0
        mock_fetch.assert_not_called()
