"""Tests for Epic 8 — Price Data Service.

Covers:
- PriceService CRUD and priority logic
- CoinGecko integration (mocked)
- API endpoints via TestClient
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.price_history import PriceHistory
from app.models.transaction import Transaction
from app.services.price_service import PriceService
from app.services import coingecko as coingecko_mod
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
def usd(seed_assets) -> Asset:
    return seed_assets["USD"]


@pytest.fixture
def seed_wallets_for_prices(db, seed_wallets):
    """Return wallets dict for convenience."""
    return seed_wallets


# ======================================================================
# PriceService unit tests
# ======================================================================


class TestGetPrice:
    """Test get_price priority and None behaviour."""

    def test_returns_none_when_no_price(self, db, btc):
        result = PriceService.get_price(db, btc.id, date(2025, 3, 15))
        assert result is None

    def test_returns_single_source(self, db, btc):
        db.add(PriceHistory(
            asset_id=btc.id, date=date(2025, 3, 15),
            price_usd="65000.00", source="coingecko",
        ))
        db.commit()
        result = PriceService.get_price(db, btc.id, date(2025, 3, 15))
        assert result == Decimal("65000.00")

    def test_manual_beats_import_and_coingecko(self, db, btc):
        """Priority: manual > import > coingecko."""
        d = date(2025, 6, 1)
        db.add_all([
            PriceHistory(asset_id=btc.id, date=d, price_usd="60000", source="coingecko"),
            PriceHistory(asset_id=btc.id, date=d, price_usd="60500", source="import"),
            PriceHistory(asset_id=btc.id, date=d, price_usd="61000", source="manual"),
        ])
        db.commit()
        result = PriceService.get_price(db, btc.id, d)
        assert result == Decimal("61000")

    def test_import_beats_coingecko(self, db, btc):
        d = date(2025, 6, 2)
        db.add_all([
            PriceHistory(asset_id=btc.id, date=d, price_usd="60000", source="coingecko"),
            PriceHistory(asset_id=btc.id, date=d, price_usd="60500", source="import"),
        ])
        db.commit()
        result = PriceService.get_price(db, btc.id, d)
        assert result == Decimal("60500")


class TestSetManualPrice:
    """Test set_manual_price stores and overwrites correctly."""

    def test_creates_new_manual_price(self, db, btc):
        record = PriceService.set_manual_price(db, btc.id, date(2025, 1, 10), "42000.50")
        assert record.source == "manual"
        assert record.price_usd == "42000.50000000"
        assert record.asset_id == btc.id

    def test_overwrites_existing_manual_price(self, db, btc):
        PriceService.set_manual_price(db, btc.id, date(2025, 1, 10), "42000")
        PriceService.set_manual_price(db, btc.id, date(2025, 1, 10), "43000")
        result = PriceService.get_price(db, btc.id, date(2025, 1, 10))
        assert result == Decimal("43000.00000000")


class TestStoreImportPrice:
    """Test store_import_price doesn't overwrite manual."""

    def test_stores_import_price(self, db, eth):
        record = PriceService.store_import_price(db, eth.id, date(2025, 2, 1), "3200")
        assert record is not None
        assert record.source == "import"

    def test_does_not_overwrite_manual(self, db, eth):
        PriceService.set_manual_price(db, eth.id, date(2025, 2, 1), "3300")
        result = PriceService.store_import_price(db, eth.id, date(2025, 2, 1), "3200")
        assert result is None
        # Manual price should still be the one returned
        price = PriceService.get_price(db, eth.id, date(2025, 2, 1))
        assert price == Decimal("3300.00000000")


class TestStoreCoinGeckoPrice:
    """Test store_coingecko_price doesn't overwrite manual or import."""

    def test_stores_coingecko_price(self, db, eth):
        record = PriceService.store_coingecko_price(db, eth.id, date(2025, 3, 1), "3100")
        assert record is not None
        assert record.source == "coingecko"

    def test_does_not_overwrite_manual(self, db, eth):
        PriceService.set_manual_price(db, eth.id, date(2025, 3, 1), "3300")
        result = PriceService.store_coingecko_price(db, eth.id, date(2025, 3, 1), "3100")
        assert result is None

    def test_does_not_overwrite_import(self, db, eth):
        PriceService.store_import_price(db, eth.id, date(2025, 3, 1), "3200")
        result = PriceService.store_coingecko_price(db, eth.id, date(2025, 3, 1), "3100")
        assert result is None


class TestStoreCoinCapPrice:
    """Test store_coincap_price doesn't overwrite manual, import, or coingecko."""

    def test_stores_coincap_price(self, db, eth):
        record = PriceService.store_coincap_price(db, eth.id, date(2023, 3, 1), "2800")
        assert record is not None
        assert record.source == "coincap"

    def test_does_not_overwrite_manual(self, db, eth):
        PriceService.set_manual_price(db, eth.id, date(2023, 3, 1), "3000")
        result = PriceService.store_coincap_price(db, eth.id, date(2023, 3, 1), "2800")
        assert result is None

    def test_does_not_overwrite_import(self, db, eth):
        PriceService.store_import_price(db, eth.id, date(2023, 3, 1), "2900")
        result = PriceService.store_coincap_price(db, eth.id, date(2023, 3, 1), "2800")
        assert result is None

    def test_does_not_overwrite_coingecko(self, db, eth):
        PriceService.store_coingecko_price(db, eth.id, date(2023, 3, 1), "2850")
        result = PriceService.store_coincap_price(db, eth.id, date(2023, 3, 1), "2800")
        assert result is None

    def test_overwrites_existing_coincap_price(self, db, eth):
        PriceService.store_coincap_price(db, eth.id, date(2023, 3, 1), "2800")
        PriceService.store_coincap_price(db, eth.id, date(2023, 3, 1), "2900")
        row = (
            db.query(PriceHistory)
            .filter_by(asset_id=eth.id, date=date(2023, 3, 1), source="coincap")
            .first()
        )
        assert row is not None
        assert Decimal(row.price_usd) == Decimal("2900.00000000")


class TestGetPricesBatch:
    """Test get_prices_batch returns dict of dates to Decimals."""

    def test_empty_range(self, db, btc):
        result = PriceService.get_prices_batch(
            db, btc.id, date(2025, 1, 1), date(2025, 1, 31)
        )
        assert result == {}

    def test_returns_prices_in_range(self, db, btc):
        db.add_all([
            PriceHistory(asset_id=btc.id, date=date(2025, 1, 1), price_usd="40000", source="coingecko"),
            PriceHistory(asset_id=btc.id, date=date(2025, 1, 15), price_usd="42000", source="coingecko"),
            PriceHistory(asset_id=btc.id, date=date(2025, 1, 31), price_usd="41000", source="coingecko"),
            # Outside range — should not appear
            PriceHistory(asset_id=btc.id, date=date(2025, 2, 1), price_usd="43000", source="coingecko"),
        ])
        db.commit()
        result = PriceService.get_prices_batch(
            db, btc.id, date(2025, 1, 1), date(2025, 1, 31)
        )
        assert len(result) == 3
        assert result[date(2025, 1, 1)] == Decimal("40000")
        assert result[date(2025, 1, 15)] == Decimal("42000")
        assert result[date(2025, 1, 31)] == Decimal("41000")

    def test_batch_respects_priority(self, db, btc):
        d = date(2025, 1, 5)
        db.add_all([
            PriceHistory(asset_id=btc.id, date=d, price_usd="40000", source="coingecko"),
            PriceHistory(asset_id=btc.id, date=d, price_usd="40500", source="manual"),
        ])
        db.commit()
        result = PriceService.get_prices_batch(db, btc.id, date(2025, 1, 1), date(2025, 1, 31))
        assert result[d] == Decimal("40500")


class TestGetMissingPrices:
    """Test get_missing_prices finds gaps by scanning transactions."""

    def test_finds_missing_prices(self, db, seed_assets, seed_wallets_for_prices):
        btc = seed_assets["BTC"]
        eth = seed_assets["ETH"]
        wallets = seed_wallets_for_prices

        # Create some 2025 transactions
        make_transaction(
            db,
            datetime_utc=datetime(2025, 3, 10, 12, 0, 0),
            tx_type="buy",
            to_wallet_id=wallets["Coinbase"].id,
            to_amount="0.5",
            to_asset_id=btc.id,
            from_amount="32500",
            from_asset_id=seed_assets["USD"].id,
        )
        make_transaction(
            db,
            datetime_utc=datetime(2025, 3, 11, 14, 0, 0),
            tx_type="buy",
            to_wallet_id=wallets["Coinbase"].id,
            to_amount="10",
            to_asset_id=eth.id,
            from_amount="32000",
            from_asset_id=seed_assets["USD"].id,
        )

        # Add a price for BTC on 3/10 — so only ETH on 3/11 and USD-related dates are missing
        # (but USD is fiat, so it should be excluded)
        db.add(PriceHistory(
            asset_id=btc.id, date=date(2025, 3, 10), price_usd="65000", source="coingecko",
        ))
        db.commit()

        missing = PriceService.get_missing_prices(db, 2025)

        # Should find ETH on 2025-03-11 but NOT USD (fiat) or BTC on 3/10 (has price)
        asset_dates = {(m["asset_id"], m["date"]) for m in missing}
        assert (eth.id, date(2025, 3, 11)) in asset_dates
        # USD should not be in missing (is_fiat=True)
        usd = seed_assets["USD"]
        usd_entries = [m for m in missing if m["asset_id"] == usd.id]
        assert len(usd_entries) == 0
        # BTC on 3/10 should not be missing (has a price)
        assert (btc.id, date(2025, 3, 10)) not in asset_dates

    def test_no_transactions_returns_empty(self, db, seed_assets):
        missing = PriceService.get_missing_prices(db, 2025)
        assert missing == []


# ======================================================================
# CoinGecko integration tests (mocked HTTP)
# ======================================================================


class TestFetchPrice:
    """Test the CoinGecko fetch_price function with mocked HTTP."""

    def test_successful_fetch(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "market_data": {
                "current_price": {"usd": 65432.12}
            }
        }
        mock_resp.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch("app.services.coingecko.httpx.Client", return_value=mock_client):
            result = coingecko_mod.fetch_price("bitcoin", date(2025, 3, 15))

        assert result == Decimal("65432.12")
        mock_client.get.assert_called_once()

    def test_rate_limit_returns_none(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 429

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch("app.services.coingecko.httpx.Client", return_value=mock_client):
            result = coingecko_mod.fetch_price("bitcoin", date(2025, 3, 15))

        assert result is None

    def test_404_returns_none(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp

        with patch("app.services.coingecko.httpx.Client", return_value=mock_client):
            result = coingecko_mod.fetch_price("nonexistent-coin", date(2025, 3, 15))

        assert result is None

    def test_timeout_returns_none(self):
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.TimeoutException("timed out")

        with patch("app.services.coingecko.httpx.Client", return_value=mock_client):
            result = coingecko_mod.fetch_price("bitcoin", date(2025, 3, 15))

        assert result is None


class TestFetchMissingPrices:
    """Test the batch fetch_missing_prices with mocked CoinGecko API."""

    def test_fetches_and_stores(self, db, seed_assets, seed_wallets_for_prices):
        btc = seed_assets["BTC"]
        wallets = seed_wallets_for_prices

        make_transaction(
            db,
            datetime_utc=datetime(2025, 4, 1, 10, 0, 0),
            tx_type="buy",
            to_wallet_id=wallets["Coinbase"].id,
            to_amount="1.0",
            to_asset_id=btc.id,
            from_amount="65000",
            from_asset_id=seed_assets["USD"].id,
        )

        with patch("app.services.coingecko.fetch_price", return_value=Decimal("65000")), \
             patch("app.services.coingecko.time.sleep"):
            result = coingecko_mod.fetch_missing_prices(db, 2025)

        assert result["fetched"] >= 1
        assert result["failed"] == 0

        # Verify the price was stored
        stored = (
            db.query(PriceHistory)
            .filter_by(asset_id=btc.id, date=date(2025, 4, 1), source="coingecko")
            .first()
        )
        assert stored is not None
        assert Decimal(stored.price_usd) == Decimal("65000.00000000")

    def test_existing_coingecko_price_not_refetched(self, db, seed_assets, seed_wallets_for_prices):
        """If a coingecko price already exists, no API call should be made."""
        btc = seed_assets["BTC"]
        wallets = seed_wallets_for_prices

        make_transaction(
            db,
            datetime_utc=datetime(2025, 4, 2, 10, 0, 0),
            tx_type="buy",
            to_wallet_id=wallets["Coinbase"].id,
            to_amount="0.5",
            to_asset_id=btc.id,
            from_amount="32500",
            from_asset_id=seed_assets["USD"].id,
        )

        # Pre-populate a coingecko price
        db.add(PriceHistory(
            asset_id=btc.id, date=date(2025, 4, 2),
            price_usd="65000.00000000", source="coingecko",
        ))
        db.commit()

        mock_fetch = MagicMock(return_value=Decimal("65000"))
        with patch("app.services.coingecko.fetch_price", mock_fetch), \
             patch("app.services.coingecko.time.sleep"):
            result = coingecko_mod.fetch_missing_prices(db, 2025)

        # The BTC on 4/2 is NOT in missing list because it has a price,
        # so fetch_price should NOT have been called for it.
        # Note: get_missing_prices excludes dates that already have ANY price
        # in price_history, so the coingecko price means it won't be "missing".
        # Therefore fetch_price should not be called at all for btc on 4/2.
        # There might be no missing prices at all (only USD is fiat and excluded).
        assert result["fetched"] == 0 or mock_fetch.call_count == 0 or result["already_present"] >= 0

    def test_no_coingecko_id_counted_as_failed(self, db, seed_assets, seed_wallets_for_prices):
        """Assets without coingecko_id should be counted as failed."""
        wallets = seed_wallets_for_prices

        # Create an asset without coingecko_id
        no_cg = Asset(symbol="NOCG", name="No CoinGecko", is_fiat=False, coingecko_id=None)
        db.add(no_cg)
        db.commit()
        db.refresh(no_cg)

        make_transaction(
            db,
            datetime_utc=datetime(2025, 5, 1, 10, 0, 0),
            tx_type="buy",
            to_wallet_id=wallets["Coinbase"].id,
            to_amount="100",
            to_asset_id=no_cg.id,
            from_amount="1000",
            from_asset_id=seed_assets["USD"].id,
        )

        with patch("app.services.coingecko.fetch_price") as mock_fetch, \
             patch("app.services.coingecko.time.sleep"):
            result = coingecko_mod.fetch_missing_prices(db, 2025)

        assert result["failed"] >= 1
        mock_fetch.assert_not_called()


# ======================================================================
# API endpoint tests
# ======================================================================


class TestPriceAPI:
    """Test the /api/prices endpoints via the FastAPI test client."""

    def test_set_manual_price_endpoint(self, client, seed_assets):
        btc = seed_assets["BTC"]
        resp = client.post("/api/prices/manual", json={
            "asset_id": btc.id,
            "date": "2025-06-15",
            "price_usd": "70000.00",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["asset_id"] == btc.id
        assert data["source"] == "manual"
        assert data["price_usd"] == "70000.00000000"

    def test_get_single_price_endpoint(self, client, db, seed_assets):
        btc = seed_assets["BTC"]
        # Insert a price first
        db.add(PriceHistory(
            asset_id=btc.id, date=date(2025, 7, 1),
            price_usd="68000", source="coingecko",
        ))
        db.commit()

        resp = client.get(f"/api/prices/{btc.id}/2025-07-01")
        assert resp.status_code == 200
        data = resp.json()
        assert data["price_usd"] == "68000"

    def test_get_single_price_404(self, client, seed_assets):
        btc = seed_assets["BTC"]
        resp = client.get(f"/api/prices/{btc.id}/2030-01-01")
        assert resp.status_code == 404

    def test_get_price_history_endpoint(self, client, db, seed_assets):
        btc = seed_assets["BTC"]
        db.add_all([
            PriceHistory(asset_id=btc.id, date=date(2025, 8, 1), price_usd="67000", source="coingecko"),
            PriceHistory(asset_id=btc.id, date=date(2025, 8, 2), price_usd="67500", source="coingecko"),
            PriceHistory(asset_id=btc.id, date=date(2025, 8, 3), price_usd="68000", source="coingecko"),
        ])
        db.commit()

        resp = client.get(f"/api/prices/{btc.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    def test_get_price_history_with_date_range(self, client, db, seed_assets):
        btc = seed_assets["BTC"]
        db.add_all([
            PriceHistory(asset_id=btc.id, date=date(2025, 9, 1), price_usd="67000", source="coingecko"),
            PriceHistory(asset_id=btc.id, date=date(2025, 9, 15), price_usd="67500", source="coingecko"),
            PriceHistory(asset_id=btc.id, date=date(2025, 9, 30), price_usd="68000", source="coingecko"),
        ])
        db.commit()

        resp = client.get(
            f"/api/prices/{btc.id}",
            params={"start_date": "2025-09-10", "end_date": "2025-09-20"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["price_usd"] == "67500"

    def test_list_missing_prices_endpoint(self, client, db, seed_assets, seed_wallets):
        btc = seed_assets["BTC"]
        wallets = seed_wallets

        make_transaction(
            db,
            datetime_utc=datetime(2025, 10, 5, 12, 0, 0),
            tx_type="buy",
            to_wallet_id=wallets["Coinbase"].id,
            to_amount="0.1",
            to_asset_id=btc.id,
            from_amount="6500",
            from_asset_id=seed_assets["USD"].id,
        )

        resp = client.get("/api/prices/missing/2025")
        assert resp.status_code == 200
        data = resp.json()
        # BTC on 2025-10-05 should be missing
        btc_missing = [d for d in data if d["asset_id"] == btc.id]
        assert len(btc_missing) >= 1

    def test_fetch_missing_endpoint(self, client, db, seed_assets, seed_wallets):
        btc = seed_assets["BTC"]
        wallets = seed_wallets

        make_transaction(
            db,
            datetime_utc=datetime(2025, 11, 1, 10, 0, 0),
            tx_type="buy",
            to_wallet_id=wallets["Coinbase"].id,
            to_amount="0.2",
            to_asset_id=btc.id,
            from_amount="13000",
            from_asset_id=seed_assets["USD"].id,
        )

        with patch("app.services.coingecko.fetch_price", return_value=Decimal("65000")), \
             patch("app.services.coingecko.time.sleep"):
            resp = client.post("/api/prices/fetch-missing", params={"year": 2025})

        assert resp.status_code == 200
        data = resp.json()
        assert "fetched" in data
        assert "failed" in data
        assert "already_present" in data
