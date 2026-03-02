"""Tests for coingecko — price fetching and auto-mapping."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch, MagicMock

import httpx

from app.services.coingecko import (
    fetch_price,
    fetch_current_prices,
    auto_map_coingecko_ids,
    SYMBOL_TO_COINGECKO,
)
from app.tests.factories import create_asset, create_wallet


class TestFetchPrice:
    def test_successful_fetch(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "market_data": {
                "current_price": {"usd": 50123.45}
            }
        }
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.coingecko.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=MagicMock(
                get=MagicMock(return_value=mock_response)
            ))
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = fetch_price("bitcoin", date(2025, 1, 15))
            assert result == Decimal("50123.45")

    def test_rate_limiting_returns_none(self):
        mock_response = MagicMock()
        mock_response.status_code = 429

        with patch("app.services.coingecko.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=MagicMock(
                get=MagicMock(return_value=mock_response)
            ))
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = fetch_price("bitcoin", date(2025, 1, 15))
            assert result is None

    def test_404_returns_none(self):
        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("app.services.coingecko.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=MagicMock(
                get=MagicMock(return_value=mock_response)
            ))
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = fetch_price("unknown-coin", date(2025, 1, 15))
            assert result is None

    def test_timeout_returns_none(self):
        with patch("app.services.coingecko.httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.get.side_effect = httpx.TimeoutException("Connection timed out")
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = fetch_price("bitcoin", date(2025, 1, 15))
            assert result is None

    def test_missing_usd_price_returns_none(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"market_data": {"current_price": {}}}
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.coingecko.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=MagicMock(
                get=MagicMock(return_value=mock_response)
            ))
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = fetch_price("bitcoin", date(2025, 1, 15))
            assert result is None


class TestFetchCurrentPrices:
    def test_successful_batch_fetch(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "bitcoin": {"usd": 50000},
            "ethereum": {"usd": 3000},
        }
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.coingecko.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=MagicMock(
                get=MagicMock(return_value=mock_response)
            ))
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = fetch_current_prices(["bitcoin", "ethereum"])
            assert result["bitcoin"] == Decimal("50000")
            assert result["ethereum"] == Decimal("3000")

    def test_empty_input_returns_empty(self):
        result = fetch_current_prices([])
        assert result == {}

    def test_rate_limit_returns_empty(self):
        mock_response = MagicMock()
        mock_response.status_code = 429

        with patch("app.services.coingecko.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=MagicMock(
                get=MagicMock(return_value=mock_response)
            ))
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = fetch_current_prices(["bitcoin"])
            assert result == {}


class TestAutoMapCoingeckoIds:
    def test_maps_known_symbols(self, db):
        btc = create_asset(db, symbol="BTC", coingecko_id=None)
        eth = create_asset(db, symbol="ETH", coingecko_id=None)
        db.commit()

        updated = auto_map_coingecko_ids(db)
        assert updated == 2

        db.refresh(btc)
        db.refresh(eth)
        assert btc.coingecko_id == "bitcoin"
        assert eth.coingecko_id == "ethereum"

    def test_skips_already_mapped(self, db):
        create_asset(db, symbol="BTC", coingecko_id="bitcoin")
        db.commit()

        updated = auto_map_coingecko_ids(db)
        assert updated == 0

    def test_skips_unknown_symbols(self, db):
        create_asset(db, symbol="UNKNOWNCOIN", coingecko_id=None)
        db.commit()

        updated = auto_map_coingecko_ids(db)
        assert updated == 0


class TestFetchPriceErrors:
    def test_http_status_error_returns_none(self):
        """HTTPStatusError (e.g. 500) returns None."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )

        with patch("app.services.coingecko.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=MagicMock(
                get=MagicMock(return_value=mock_response)
            ))
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = fetch_price("bitcoin", date(2025, 1, 15))
            assert result is None

    def test_generic_exception_returns_none(self):
        """Unexpected exception returns None."""
        with patch("app.services.coingecko.httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.get.side_effect = RuntimeError("unexpected")
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = fetch_price("bitcoin", date(2025, 1, 15))
            assert result is None


class TestFetchCurrentPricesErrors:
    def test_timeout_returns_empty(self):
        """TimeoutException returns empty dict."""
        with patch("app.services.coingecko.httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.get.side_effect = httpx.TimeoutException("timeout")
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = fetch_current_prices(["bitcoin"])
            assert result == {}

    def test_http_status_error_returns_empty(self):
        """HTTPStatusError returns empty dict."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )

        with patch("app.services.coingecko.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=MagicMock(
                get=MagicMock(return_value=mock_response)
            ))
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = fetch_current_prices(["bitcoin"])
            assert result == {}

    def test_generic_exception_returns_empty(self):
        """Unexpected exception returns empty dict."""
        with patch("app.services.coingecko.httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.get.side_effect = RuntimeError("unexpected")
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = fetch_current_prices(["bitcoin"])
            assert result == {}


class TestFetchChartChunk:
    def test_successful_chart_fetch(self):
        """Successful chart fetch returns (date, price) tuples."""
        from app.services.coingecko import _fetch_chart_chunk

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "prices": [
                [1704067200000, 42000.5],  # 2024-01-01
                [1704153600000, 43000.0],  # 2024-01-02
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.coingecko.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=MagicMock(
                get=MagicMock(return_value=mock_response)
            ))
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = _fetch_chart_chunk("bitcoin", 30)
            assert result is not None
            assert len(result) == 2
            assert isinstance(result[0][1], Decimal)

    def test_deduplicates_same_date(self):
        """Duplicate dates in chart are deduplicated."""
        from app.services.coingecko import _fetch_chart_chunk

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "prices": [
                [1704067200000, 42000.0],
                [1704070800000, 42100.0],  # Same day, different time
            ]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("app.services.coingecko.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=MagicMock(
                get=MagicMock(return_value=mock_response)
            ))
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = _fetch_chart_chunk("bitcoin", 1)
            assert result is not None
            assert len(result) == 1

    def test_404_returns_none(self):
        """404 on chart returns None."""
        from app.services.coingecko import _fetch_chart_chunk

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("app.services.coingecko.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=MagicMock(
                get=MagicMock(return_value=mock_response)
            ))
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = _fetch_chart_chunk("unknown-coin", 30)
            assert result is None

    def test_timeout_returns_none(self):
        """Timeout on chart returns None."""
        from app.services.coingecko import _fetch_chart_chunk

        with patch("app.services.coingecko.httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.get.side_effect = httpx.TimeoutException("timeout")
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = _fetch_chart_chunk("bitcoin", 30)
            assert result is None

    def test_http_error_returns_none(self):
        """HTTP error on chart returns None."""
        from app.services.coingecko import _fetch_chart_chunk

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Error", request=MagicMock(), response=MagicMock(status_code=503),
        )

        with patch("app.services.coingecko.httpx.Client") as MockClient:
            MockClient.return_value.__enter__ = MagicMock(return_value=MagicMock(
                get=MagicMock(return_value=mock_response)
            ))
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = _fetch_chart_chunk("bitcoin", 30)
            assert result is None

    def test_generic_exception_returns_none(self):
        """Generic exception on chart returns None."""
        from app.services.coingecko import _fetch_chart_chunk

        with patch("app.services.coingecko.httpx.Client") as MockClient:
            mock_client = MagicMock()
            mock_client.get.side_effect = RuntimeError("unexpected")
            MockClient.return_value.__enter__ = MagicMock(return_value=mock_client)
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = _fetch_chart_chunk("bitcoin", 30)
            assert result is None

    def test_429_retries_then_exhausted(self):
        """429 retries and exhausts retries returns None."""
        from app.services.coingecko import _fetch_chart_chunk

        mock_response = MagicMock()
        mock_response.status_code = 429

        with (
            patch("app.services.coingecko.httpx.Client") as MockClient,
            patch("app.services.coingecko.time.sleep"),
        ):
            MockClient.return_value.__enter__ = MagicMock(return_value=MagicMock(
                get=MagicMock(return_value=mock_response)
            ))
            MockClient.return_value.__exit__ = MagicMock(return_value=False)

            result = _fetch_chart_chunk("bitcoin", 30, retries=2)
            assert result is None


class TestFetchPriceRange:
    def test_calls_chart_chunk(self):
        """fetch_price_range delegates to _fetch_chart_chunk."""
        from app.services.coingecko import fetch_price_range

        with patch("app.services.coingecko._fetch_chart_chunk") as mock_chunk:
            mock_chunk.return_value = [(date(2025, 1, 1), Decimal("42000"))]
            result = fetch_price_range("bitcoin", date(2025, 1, 1), date(2025, 1, 10))
            assert result is not None
            assert len(result) == 1
            mock_chunk.assert_called_once_with("bitcoin", 10)

    def test_caps_at_365_days(self):
        """Long ranges are capped at 365 days."""
        from app.services.coingecko import fetch_price_range

        with patch("app.services.coingecko._fetch_chart_chunk") as mock_chunk:
            mock_chunk.return_value = []
            fetch_price_range("bitcoin", date(2020, 1, 1), date(2025, 1, 1))
            mock_chunk.assert_called_once_with("bitcoin", 365)


class TestFetchMissingPrices:
    def test_already_present(self, db):
        """Prices already in DB are counted as already_present."""
        from app.services.coingecko import fetch_missing_prices
        from app.models.price_history import PriceHistory

        asset = create_asset(db, symbol="BTC", coingecko_id="bitcoin")
        db.commit()

        # Add existing coingecko price
        ph = PriceHistory(
            asset_id=asset.id, date=date(2025, 1, 15),
            price_usd="42000.00", source="coingecko",
        )
        db.add(ph)
        db.commit()

        with patch("app.services.coingecko.PriceService") as MockPS:
            MockPS.get_missing_prices.return_value = [
                {"asset_id": asset.id, "date": date(2025, 1, 15)},
            ]
            result = fetch_missing_prices(db, 2025)
            assert result["already_present"] == 1
            assert result["fetched"] == 0

    def test_no_coingecko_id(self, db):
        """Asset without coingecko_id counts as failed."""
        from app.services.coingecko import fetch_missing_prices

        asset = create_asset(db, symbol="OBSCURE", coingecko_id=None)
        db.commit()

        with patch("app.services.coingecko.PriceService") as MockPS:
            MockPS.get_missing_prices.return_value = [
                {"asset_id": asset.id, "date": date(2025, 1, 15)},
            ]
            result = fetch_missing_prices(db, 2025)
            assert result["failed"] == 1
            assert result["fetched"] == 0

    def test_fetch_returns_none_counts_as_failed(self, db):
        """When fetch_price returns None, count as failed."""
        from app.services.coingecko import fetch_missing_prices

        asset = create_asset(db, symbol="BTC", coingecko_id="bitcoin")
        db.commit()

        with (
            patch("app.services.coingecko.PriceService") as MockPS,
            patch("app.services.coingecko.fetch_price", return_value=None),
            patch("app.services.coingecko.time.sleep"),
        ):
            MockPS.get_missing_prices.return_value = [
                {"asset_id": asset.id, "date": date(2025, 1, 15)},
            ]
            result = fetch_missing_prices(db, 2025)
            assert result["failed"] == 1

    def test_successful_fetch_stores_price(self, db):
        """Successful fetch stores the price and counts as fetched."""
        from app.services.coingecko import fetch_missing_prices

        asset = create_asset(db, symbol="BTC", coingecko_id="bitcoin")
        db.commit()

        with (
            patch("app.services.coingecko.PriceService") as MockPS,
            patch("app.services.coingecko.fetch_price", return_value=Decimal("42000")),
            patch("app.services.coingecko.time.sleep"),
        ):
            MockPS.get_missing_prices.return_value = [
                {"asset_id": asset.id, "date": date(2025, 1, 15)},
            ]
            result = fetch_missing_prices(db, 2025)
            assert result["fetched"] == 1
            MockPS.store_coingecko_price.assert_called_once()


class TestRefreshCurrentPrices:
    def _make_held_lot(self, db):
        """Helper: create an asset with an open lot for refresh tests."""
        from app.models import TaxLot
        from app.tests.factories import create_transaction

        asset = create_asset(db, symbol="BTC", coingecko_id="bitcoin")
        wallet = create_wallet(db, name="Coinbase")
        db.commit()

        tx = create_transaction(
            db, tx_type="buy", to_wallet_id=wallet.id,
            to_asset_id=asset.id, to_amount="1.0", to_value_usd="30000.00",
        )
        db.commit()

        lot = TaxLot(
            wallet_id=wallet.id, asset_id=asset.id,
            amount="1.0", remaining_amount="1.0",
            cost_basis_usd="30000.00", cost_basis_per_unit="30000.00",
            acquired_date=date(2025, 1, 1),
            acquisition_tx_id=tx.id,
            source_type="purchase",
        )
        db.add(lot)
        db.commit()
        return asset, wallet

    def test_no_held_assets(self, db):
        """With no held assets, returns zeros."""
        from app.services.coingecko import refresh_current_prices

        result = refresh_current_prices(db)
        assert result["updated"] == 0
        assert result["failed"] == 0

    def test_held_assets_fetched(self, db):
        """Held assets are fetched and stored."""
        from app.services.coingecko import refresh_current_prices

        self._make_held_lot(db)

        with (
            patch("app.services.coingecko.fetch_current_prices") as mock_fetch,
            patch("app.services.coingecko.PriceService") as MockPS,
        ):
            mock_fetch.return_value = {"bitcoin": Decimal("50000")}
            MockPS.store_coingecko_price.return_value = True
            result = refresh_current_prices(db)
            assert result["updated"] == 1

    def test_held_assets_failed_price(self, db):
        """When batch fetch returns no price for an asset, count as failed."""
        from app.services.coingecko import refresh_current_prices

        self._make_held_lot(db)

        with (
            patch("app.services.coingecko.fetch_current_prices") as mock_fetch,
        ):
            mock_fetch.return_value = {}  # No prices returned
            result = refresh_current_prices(db)
            assert result["failed"] == 1


class TestBackfillHistoricalPrices:
    def _make_held_lot(self, db):
        """Helper: create an asset with a lot for backfill tests."""
        from app.models import TaxLot
        from app.tests.factories import create_transaction

        asset = create_asset(db, symbol="BTC", coingecko_id="bitcoin")
        wallet = create_wallet(db, name="Coinbase")
        db.commit()

        tx = create_transaction(
            db, tx_type="buy", to_wallet_id=wallet.id,
            to_asset_id=asset.id, to_amount="1.0", to_value_usd="30000.00",
        )
        db.commit()

        lot = TaxLot(
            wallet_id=wallet.id, asset_id=asset.id,
            amount="1.0", remaining_amount="1.0",
            cost_basis_usd="30000.00", cost_basis_per_unit="30000.00",
            acquired_date=date(2025, 1, 1),
            acquisition_tx_id=tx.id,
            source_type="purchase",
        )
        db.add(lot)
        db.commit()
        return asset, wallet

    def test_no_held_assets(self, db):
        """With no assets, returns zeros."""
        from app.services.coingecko import backfill_historical_prices

        result = backfill_historical_prices(db)
        assert result["total_stored"] == 0
        assert result["assets_processed"] == 0

    def test_deadline_reached(self, db):
        """When deadline is reached, remaining assets are skipped."""
        from app.services.coingecko import backfill_historical_prices

        self._make_held_lot(db)

        # Set deadline_seconds=0 so it immediately hits the deadline
        result = backfill_historical_prices(db, deadline_seconds=0)
        assert result["assets_skipped"] >= 1

    def test_successful_backfill(self, db):
        """Successful backfill stores prices and counts them."""
        from app.services.coingecko import backfill_historical_prices

        self._make_held_lot(db)

        with (
            patch("app.services.coingecko.fetch_price_range") as mock_range,
            patch("app.services.coingecko.PriceService") as MockPS,
            patch("app.services.coingecko.time.sleep"),
        ):
            mock_range.return_value = [
                (date(2025, 1, 1), Decimal("42000")),
                (date(2025, 1, 2), Decimal("43000")),
            ]
            MockPS.store_coingecko_price.return_value = True
            result = backfill_historical_prices(db, deadline_seconds=300)
            assert result["assets_processed"] == 1
            assert result["total_stored"] == 2

    def test_failed_fetch_range(self, db):
        """When fetch_price_range returns None, count as failed."""
        from app.services.coingecko import backfill_historical_prices

        self._make_held_lot(db)

        with (
            patch("app.services.coingecko.fetch_price_range", return_value=None),
            patch("app.services.coingecko.time.sleep"),
        ):
            result = backfill_historical_prices(db, deadline_seconds=300)
            assert result["assets_failed"] == 1
