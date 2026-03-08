"""Price Data API — Epic 8.

Endpoints for querying, storing, and fetching historical crypto prices.
"""

import logging
import threading
from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db, _get_defaults
from app.models.price_history import PriceHistory
from app.schemas.price import (
    BackfillResponse,
    BackfillStatusResponse,
    FetchMissingResponse,
    ManualPriceRequest,
    MissingPriceItem,
    PriceHistoryResponse,
    RefreshCurrentResponse,
)
from app.services.coingecko import backfill_historical_prices, fetch_missing_prices, refresh_current_prices
from app.services.price_service import PriceService

logger = logging.getLogger(__name__)

router = APIRouter()

# Background backfill state
_backfill_lock = threading.Lock()
_backfill_status: dict = {"status": "idle", "result": None, "error": None}


def _run_backfill():
    """Run backfill in a background thread with its own DB session."""
    global _backfill_status
    _, session_factory = _get_defaults()
    db = session_factory()
    try:
        def _on_progress(msg: str):
            global _backfill_status
            _backfill_status = {**_backfill_status, "progress": msg}

        result = backfill_historical_prices(db, on_progress=_on_progress)
        _backfill_status = {"status": "completed", "result": result, "error": None, "progress": None}
    except Exception as exc:
        logger.exception("Background backfill failed")
        _backfill_status = {"status": "failed", "result": None, "error": str(exc), "progress": None}
    finally:
        db.close()


@router.get("/missing/{year}", response_model=list[MissingPriceItem])
def list_missing_prices(year: int, db: Session = Depends(get_db)):
    """List all (asset, date) pairs in the tax year that need prices."""
    items = PriceService.get_missing_prices(db, year)
    return items


@router.post("/refresh-current", response_model=RefreshCurrentResponse)
def refresh_current(db: Session = Depends(get_db)):
    """Fetch current prices from CoinGecko for all held assets and store them."""
    result = refresh_current_prices(db)
    return result


@router.post("/backfill", response_model=BackfillStatusResponse)
def backfill_prices():
    """Launch backfill of historical prices in a background thread.

    Returns immediately with status. Poll GET /backfill/status for results.
    """
    global _backfill_status
    with _backfill_lock:
        if _backfill_status["status"] == "running":
            return _backfill_status
        _backfill_status = {"status": "running", "result": None, "error": None}
    t = threading.Thread(target=_run_backfill, daemon=True)
    t.start()
    return _backfill_status


@router.get("/backfill/status", response_model=BackfillStatusResponse)
def backfill_status():
    """Check the status of the background backfill job."""
    return _backfill_status


@router.post("/fetch-missing", response_model=FetchMissingResponse)
def trigger_fetch_missing(
    year: int = Query(..., description="Tax year to fetch missing prices for"),
    db: Session = Depends(get_db),
):
    """Trigger batch fetch of missing prices from CoinGecko for a tax year."""
    result = fetch_missing_prices(db, year)
    return result


@router.post("/manual", response_model=PriceHistoryResponse)
def set_manual_price(data: ManualPriceRequest, db: Session = Depends(get_db)):
    """Set or overwrite a manual price for an asset on a date."""
    try:
        Decimal(data.price_usd)
    except InvalidOperation:
        raise HTTPException(status_code=400, detail="Invalid price_usd value")

    record = PriceService.set_manual_price(
        db, data.asset_id, data.date, data.price_usd
    )
    return record


@router.get("/{asset_id}/{target_date}")
def get_single_price(asset_id: int, target_date: date, db: Session = Depends(get_db)):
    """Return the best-priority price for an asset on a specific date."""
    price = PriceService.get_price(db, asset_id, target_date)
    if price is None:
        raise HTTPException(status_code=404, detail="No price found for this asset and date")
    return {"asset_id": asset_id, "date": str(target_date), "price_usd": str(price)}


@router.get("/{asset_id}", response_model=list[PriceHistoryResponse])
def get_price_history(
    asset_id: int,
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    db: Session = Depends(get_db),
):
    """Return price history for an asset, with optional date range filtering."""
    query = db.query(PriceHistory).filter(PriceHistory.asset_id == asset_id)

    if start_date:
        query = query.filter(PriceHistory.date >= start_date)
    if end_date:
        query = query.filter(PriceHistory.date <= end_date)

    query = query.order_by(PriceHistory.date.desc())
    return query.all()
