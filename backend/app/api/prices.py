"""Price Data API — Epic 8.

Endpoints for querying, storing, and fetching historical crypto prices.
"""

from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.price_history import PriceHistory
from app.schemas.price import (
    BackfillResponse,
    FetchMissingResponse,
    ManualPriceRequest,
    MissingPriceItem,
    PriceHistoryResponse,
    RefreshCurrentResponse,
)
from app.services.coingecko import backfill_historical_prices, fetch_missing_prices, refresh_current_prices
from app.services.price_service import PriceService

router = APIRouter()


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


@router.post("/backfill", response_model=BackfillResponse)
def backfill_prices(db: Session = Depends(get_db)):
    """Fetch daily historical prices for all held assets from their earliest lot date.

    Uses CoinGecko /market_chart/range for efficient bulk fetching.
    This populates the price history needed for portfolio chart data.
    """
    result = backfill_historical_prices(db)
    return result


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
