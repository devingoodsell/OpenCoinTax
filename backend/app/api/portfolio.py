"""Portfolio endpoints — daily values, consolidated holdings, and summary stats."""

from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, and_, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Asset,
    LotAssignment,
    PriceHistory,
    TaxLot,
    Transaction,
    Wallet,
)

router = APIRouter()

TWO_PLACES = Decimal("0.01")
EIGHT_PLACES = Decimal("0.00000001")


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class DailyDataPoint(BaseModel):
    date: str
    total_value_usd: str
    cost_basis_usd: str


class DailyValuesSummary(BaseModel):
    current_value: str
    total_cost_basis: str
    unrealized_gain: str
    unrealized_gain_pct: str


class DailyValuesResponse(BaseModel):
    data_points: list[DailyDataPoint]
    summary: DailyValuesSummary


class WalletBreakdownItem(BaseModel):
    wallet_id: int
    wallet_name: str
    quantity: str
    value_usd: str | None


class HoldingItem(BaseModel):
    asset_id: int
    asset_symbol: str
    asset_name: str | None
    total_quantity: str
    total_cost_basis_usd: str
    current_price_usd: str | None
    market_value_usd: str | None
    roi_pct: str | None
    allocation_pct: str | None
    wallet_breakdown: list[WalletBreakdownItem] = []


class HoldingsResponse(BaseModel):
    holdings: list[HoldingItem]
    total_portfolio_value: str


class PortfolioStatsResponse(BaseModel):
    total_in: str
    total_out: str
    total_income: str
    total_expenses: str
    total_fees: str
    realized_gains: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ZERO = Decimal("0")
_ONE = Decimal("1")

# Stablecoins / fiat pegged to $1.00 — market value equals balance
_STABLECOIN_SYMBOLS = {"USD", "USDC", "GUSD", "USDT"}


def _dec(value: str | None) -> Decimal:
    """Safely convert a string to Decimal, defaulting to 0."""
    if value is None:
        return _ZERO
    try:
        return Decimal(value)
    except Exception:
        return _ZERO


# ---------------------------------------------------------------------------
# GET /daily-values
# ---------------------------------------------------------------------------


@router.get("/daily-values", response_model=DailyValuesResponse)
def get_daily_values(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
):
    """Return daily portfolio value for the given date range.

    For each day, sums (remaining_quantity × price) for all open lots.
    """

    # 1. Get all lots that were open at some point in the range.
    #    A lot is "open on day D" if acquired_date <= D and either
    #    still open (is_fully_disposed=False) or was disposed after D.
    lots = (
        db.query(
            TaxLot.id,
            TaxLot.asset_id,
            TaxLot.remaining_amount,
            TaxLot.amount,
            TaxLot.cost_basis_usd,
            TaxLot.cost_basis_per_unit,
            TaxLot.acquired_date,
            TaxLot.is_fully_disposed,
        )
        .join(Asset, TaxLot.asset_id == Asset.id)
        .filter(TaxLot.acquired_date <= datetime.combine(end_date, datetime.max.time()))
        .filter(Asset.is_hidden == False)
        .all()
    )

    if not lots:
        return DailyValuesResponse(
            data_points=[],
            summary=DailyValuesSummary(
                current_value="0.00",
                total_cost_basis="0.00",
                unrealized_gain="0.00",
                unrealized_gain_pct="0.00",
            ),
        )

    # Collect unique asset IDs
    asset_ids = list({lot.asset_id for lot in lots})

    # Identify stablecoin assets — always priced at $1.00
    stablecoin_asset_ids = set(
        row[0] for row in db.query(Asset.id)
        .filter(Asset.id.in_(asset_ids), Asset.symbol.in_(_STABLECOIN_SYMBOLS))
        .all()
    )

    # 2. Fetch all price data for these assets in the range
    prices = (
        db.query(PriceHistory.asset_id, PriceHistory.date, PriceHistory.price_usd)
        .filter(
            PriceHistory.asset_id.in_(asset_ids),
            PriceHistory.date >= start_date,
            PriceHistory.date <= end_date,
        )
        .order_by(PriceHistory.asset_id, PriceHistory.date)
        .all()
    )

    # Build price lookup: {(asset_id, date) -> Decimal}
    price_map: dict[tuple[int, date], Decimal] = {}
    for p in prices:
        key = (p.asset_id, p.date)
        if key not in price_map:
            price_map[key] = _dec(p.price_usd)

    # Also fetch prices just before the range for forward-fill
    pre_prices = (
        db.query(PriceHistory.asset_id, PriceHistory.date, PriceHistory.price_usd)
        .filter(
            PriceHistory.asset_id.in_(asset_ids),
            PriceHistory.date < start_date,
        )
        .order_by(PriceHistory.asset_id, PriceHistory.date.desc())
        .all()
    )
    # Last known price before range per asset
    last_known_before: dict[int, Decimal] = {}
    for p in pre_prices:
        if p.asset_id not in last_known_before:
            last_known_before[p.asset_id] = _dec(p.price_usd)

    # 3. Get disposal dates for lots that are fully disposed (to know when they closed)
    #    We only need to know the latest disposal for lots that may have closed during range.
    disposed_lot_ids = [lot.id for lot in lots if lot.is_fully_disposed]
    disposal_dates: dict[int, date] = {}
    if disposed_lot_ids:
        disposal_rows = (
            db.query(
                LotAssignment.tax_lot_id,
                func.max(Transaction.datetime_utc).label("last_disposal"),
            )
            .join(Transaction, LotAssignment.disposal_tx_id == Transaction.id)
            .filter(LotAssignment.tax_lot_id.in_(disposed_lot_ids))
            .group_by(LotAssignment.tax_lot_id)
            .all()
        )
        for row in disposal_rows:
            if row.last_disposal:
                disposal_dates[row.tax_lot_id] = row.last_disposal.date()

    # 4. Build list of sample dates to compute
    #    For short ranges (<= 365 days): every day
    #    For longer ranges: sample to keep ~300 data points max
    total_days = (end_date - start_date).days + 1
    max_points = 300
    step = max(1, total_days // max_points)

    sample_dates: list[date] = []
    current_day = start_date
    while current_day <= end_date:
        sample_dates.append(current_day)
        current_day += timedelta(days=step)
    # Always include the end date
    if sample_dates[-1] != end_date:
        sample_dates.append(end_date)

    # 5. Iterate through sample dates and compute portfolio value
    #    Forward-fill prices: walk through ALL dates in order but only emit
    #    data points for sample dates
    data_points: list[DailyDataPoint] = []
    last_price: dict[int, Decimal] = dict(last_known_before)
    # Force $1.00 for stablecoins
    for aid in stablecoin_asset_ids:
        last_price[aid] = _ONE
    sample_set = set(sample_dates)

    # Walk day-by-day to maintain forward-fill, but only compute lots on sample days
    walk_day = start_date
    while walk_day <= end_date:
        # Update forward-fill prices for this day
        for aid in asset_ids:
            key = (aid, walk_day)
            if key in price_map:
                if aid not in stablecoin_asset_ids:
                    last_price[aid] = price_map[key]

        if walk_day in sample_set:
            day_value = _ZERO
            day_cost_basis = _ZERO

            for lot in lots:
                # Was this lot open on walk_day?
                acquired = lot.acquired_date
                if isinstance(acquired, datetime):
                    acquired = acquired.date()
                if acquired > walk_day:
                    continue

                # If fully disposed, check if disposal happened before this day
                if lot.is_fully_disposed:
                    disposal_day = disposal_dates.get(lot.id)
                    if disposal_day is not None and disposal_day < walk_day:
                        continue

                remaining = _dec(lot.remaining_amount)
                # For disposed lots where disposal is on or after walk_day,
                # use original amount (they were fully open before disposal)
                if lot.is_fully_disposed:
                    disposal_day = disposal_dates.get(lot.id)
                    if disposal_day is not None and disposal_day >= walk_day:
                        remaining = _dec(lot.amount)

                if remaining <= _ZERO:
                    continue

                price = last_price.get(lot.asset_id, _ZERO)
                lot_value = remaining * price
                lot_cost = _dec(lot.cost_basis_per_unit) * remaining

                day_value += lot_value
                day_cost_basis += lot_cost

            data_points.append(DailyDataPoint(
                date=walk_day.isoformat(),
                total_value_usd=str(day_value.quantize(TWO_PLACES, ROUND_HALF_UP)),
                cost_basis_usd=str(day_cost_basis.quantize(TWO_PLACES, ROUND_HALF_UP)),
            ))

        walk_day += timedelta(days=1)

    # 5. Summary from the last data point
    if data_points:
        last = data_points[-1]
        first = data_points[0]
        current_val = _dec(last.total_value_usd)
        cost_basis = _dec(last.cost_basis_usd)
        unrealized = current_val - cost_basis
        pct = (
            (unrealized / cost_basis * Decimal("100")).quantize(TWO_PLACES, ROUND_HALF_UP)
            if cost_basis != _ZERO
            else _ZERO
        )
    else:
        current_val = _ZERO
        cost_basis = _ZERO
        unrealized = _ZERO
        pct = _ZERO

    return DailyValuesResponse(
        data_points=data_points,
        summary=DailyValuesSummary(
            current_value=str(current_val.quantize(TWO_PLACES, ROUND_HALF_UP)),
            total_cost_basis=str(cost_basis.quantize(TWO_PLACES, ROUND_HALF_UP)),
            unrealized_gain=str(unrealized.quantize(TWO_PLACES, ROUND_HALF_UP)),
            unrealized_gain_pct=str(pct),
        ),
    )


# ---------------------------------------------------------------------------
# GET /holdings
# ---------------------------------------------------------------------------


@router.get("/holdings", response_model=HoldingsResponse)
def get_holdings(db: Session = Depends(get_db)):
    """Return consolidated holdings aggregated across all wallets."""

    # Aggregate open lots by asset, using per-unit cost * remaining for accuracy
    # Exclude fiat assets — their balances come from transaction flows
    open_lots = (
        db.query(
            TaxLot.asset_id,
            TaxLot.wallet_id,
            TaxLot.remaining_amount,
            TaxLot.cost_basis_per_unit,
            Asset.symbol,
            Asset.name.label("asset_name"),
            Wallet.name.label("wallet_name"),
        )
        .join(Asset, TaxLot.asset_id == Asset.id)
        .join(Wallet, TaxLot.wallet_id == Wallet.id)
        .filter(TaxLot.is_fully_disposed == False, Asset.is_hidden == False, Asset.is_fiat == False)
        .all()
    )

    if not open_lots:
        return HoldingsResponse(holdings=[], total_portfolio_value="0.00")

    # Aggregate in Python to correctly handle partial disposals
    agg: dict[int, dict] = {}
    wallet_agg: dict[int, dict[int, dict]] = {}  # asset_id -> wallet_id -> {name, qty}
    for lot in open_lots:
        remaining = _dec(lot.remaining_amount)
        per_unit = _dec(lot.cost_basis_per_unit)
        if lot.asset_id not in agg:
            agg[lot.asset_id] = {
                "symbol": lot.symbol,
                "asset_name": lot.asset_name,
                "total_qty": _ZERO,
                "total_cost": _ZERO,
            }
        agg[lot.asset_id]["total_qty"] += remaining
        agg[lot.asset_id]["total_cost"] += per_unit * remaining

        # Per-wallet breakdown
        if lot.asset_id not in wallet_agg:
            wallet_agg[lot.asset_id] = {}
        wid = lot.wallet_id
        if wid not in wallet_agg[lot.asset_id]:
            wallet_agg[lot.asset_id][wid] = {"name": lot.wallet_name, "qty": _ZERO}
        wallet_agg[lot.asset_id][wid]["qty"] += remaining

    # Add fiat balances from transaction flows (not tax lots)
    fiat_assets = db.query(Asset).filter(Asset.is_fiat == True, Asset.is_hidden == False).all()
    all_wallets = db.query(Wallet).filter(Wallet.is_archived == False).all()
    for fiat_asset in fiat_assets:
        for w in all_wallets:
            inflows = (
                db.query(func.coalesce(func.sum(Transaction.to_amount), 0))
                .filter(Transaction.to_wallet_id == w.id, Transaction.to_asset_id == fiat_asset.id)
                .scalar()
            )
            outflows = (
                db.query(func.coalesce(func.sum(Transaction.from_amount), 0))
                .filter(Transaction.from_wallet_id == w.id, Transaction.from_asset_id == fiat_asset.id)
                .scalar()
            )
            net = _dec(str(inflows)) - _dec(str(outflows))
            if net > _ZERO:
                if fiat_asset.id not in agg:
                    agg[fiat_asset.id] = {
                        "symbol": fiat_asset.symbol,
                        "asset_name": fiat_asset.name,
                        "total_qty": _ZERO,
                        "total_cost": _ZERO,
                    }
                agg[fiat_asset.id]["total_qty"] += net
                agg[fiat_asset.id]["total_cost"] += net  # fiat cost basis = face value
                if fiat_asset.id not in wallet_agg:
                    wallet_agg[fiat_asset.id] = {}
                wallet_agg[fiat_asset.id][w.id] = {"name": w.name, "qty": net}

    class _Row:
        def __init__(self, asset_id, symbol, asset_name, total_qty, total_cost):
            self.asset_id = asset_id
            self.symbol = symbol
            self.asset_name = asset_name
            self.total_qty = total_qty
            self.total_cost = total_cost

    rows = [
        _Row(aid, d["symbol"], d["asset_name"], d["total_qty"], d["total_cost"])
        for aid, d in agg.items()
    ]

    # Get latest price for each asset
    asset_ids = [r.asset_id for r in rows]

    # Subquery: max date per asset
    latest_date_sq = (
        db.query(
            PriceHistory.asset_id,
            func.max(PriceHistory.date).label("max_date"),
        )
        .filter(PriceHistory.asset_id.in_(asset_ids))
        .group_by(PriceHistory.asset_id)
        .subquery()
    )

    latest_prices_rows = (
        db.query(PriceHistory.asset_id, PriceHistory.price_usd)
        .join(
            latest_date_sq,
            and_(
                PriceHistory.asset_id == latest_date_sq.c.asset_id,
                PriceHistory.date == latest_date_sq.c.max_date,
            ),
        )
        .all()
    )

    latest_price: dict[int, Decimal] = {}
    for lp in latest_prices_rows:
        if lp.asset_id not in latest_price:
            latest_price[lp.asset_id] = _dec(lp.price_usd)

    # Force $1.00 for stablecoins / USD — market value should equal balance
    for aid, d in agg.items():
        if d["symbol"].upper() in _STABLECOIN_SYMBOLS:
            latest_price[aid] = _ONE

    # Build holdings
    holdings: list[HoldingItem] = []
    total_portfolio = _ZERO

    for r in rows:
        qty = r.total_qty if isinstance(r.total_qty, Decimal) else _dec(str(r.total_qty))
        cost = r.total_cost if isinstance(r.total_cost, Decimal) else _dec(str(r.total_cost))
        price = latest_price.get(r.asset_id)

        # Build wallet breakdown for this asset
        breakdown: list[WalletBreakdownItem] = []
        if r.asset_id in wallet_agg:
            for wid, wd in wallet_agg[r.asset_id].items():
                wqty = wd["qty"]
                wvalue = None
                if price is not None and wqty > _ZERO:
                    wvalue = str((wqty * price).quantize(TWO_PLACES, ROUND_HALF_UP))
                breakdown.append(WalletBreakdownItem(
                    wallet_id=wid,
                    wallet_name=wd["name"],
                    quantity=str(wqty.quantize(EIGHT_PLACES, ROUND_HALF_UP)),
                    value_usd=wvalue,
                ))
            breakdown.sort(
                key=lambda w: _dec(w.value_usd) if w.value_usd else _ZERO,
                reverse=True,
            )

        if price is not None and qty > _ZERO:
            market_val = qty * price
            roi = (
                ((market_val - cost) / cost * Decimal("100")).quantize(TWO_PLACES, ROUND_HALF_UP)
                if cost != _ZERO
                else _ZERO
            )
            total_portfolio += market_val
            holdings.append(HoldingItem(
                asset_id=r.asset_id,
                asset_symbol=r.symbol,
                asset_name=r.asset_name,
                total_quantity=str(qty.quantize(EIGHT_PLACES, ROUND_HALF_UP)),
                total_cost_basis_usd=str(cost.quantize(TWO_PLACES, ROUND_HALF_UP)),
                current_price_usd=str(price.quantize(TWO_PLACES, ROUND_HALF_UP)),
                market_value_usd=str(market_val.quantize(TWO_PLACES, ROUND_HALF_UP)),
                roi_pct=str(roi),
                allocation_pct=None,  # filled below
                wallet_breakdown=breakdown,
            ))
        else:
            holdings.append(HoldingItem(
                asset_id=r.asset_id,
                asset_symbol=r.symbol,
                asset_name=r.asset_name,
                total_quantity=str(qty.quantize(EIGHT_PLACES, ROUND_HALF_UP)),
                total_cost_basis_usd=str(cost.quantize(TWO_PLACES, ROUND_HALF_UP)),
                current_price_usd=str(price.quantize(TWO_PLACES, ROUND_HALF_UP)) if price is not None else None,
                market_value_usd=None,
                roi_pct=None,
                allocation_pct=None,
                wallet_breakdown=breakdown,
            ))

    # Compute allocation percentages
    if total_portfolio > _ZERO:
        for h in holdings:
            if h.market_value_usd is not None:
                mv = _dec(h.market_value_usd)
                h.allocation_pct = str(
                    (mv / total_portfolio * Decimal("100")).quantize(TWO_PLACES, ROUND_HALF_UP)
                )

    # Sort by market value descending (nulls last)
    holdings.sort(
        key=lambda h: _dec(h.market_value_usd) if h.market_value_usd else _ZERO,
        reverse=True,
    )

    return HoldingsResponse(
        holdings=holdings,
        total_portfolio_value=str(total_portfolio.quantize(TWO_PLACES, ROUND_HALF_UP)),
    )


# ---------------------------------------------------------------------------
# GET /stats
# ---------------------------------------------------------------------------

# Transaction types for aggregation
_IN_TYPES = {"buy", "deposit"}
_OUT_TYPES = {"sell", "withdrawal"}
_INCOME_TYPES = {"staking_reward", "interest", "airdrop", "mining"}
_EXPENSE_TYPES = {"cost"}


@router.get("/stats", response_model=PortfolioStatsResponse)
def get_portfolio_stats(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: Session = Depends(get_db),
):
    """Aggregate transaction values for the date range."""

    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    txs = (
        db.query(
            Transaction.type,
            Transaction.from_value_usd,
            Transaction.to_value_usd,
            Transaction.net_value_usd,
            Transaction.fee_value_usd,
        )
        .filter(
            Transaction.datetime_utc >= start_dt,
            Transaction.datetime_utc <= end_dt,
        )
        .all()
    )

    total_in = _ZERO
    total_out = _ZERO
    total_income = _ZERO
    total_expenses = _ZERO
    total_fees = _ZERO

    for tx in txs:
        tx_type = tx.type
        # Value of the transaction — use the relevant USD valuation
        value = _dec(tx.to_value_usd) or _dec(tx.from_value_usd) or _dec(tx.net_value_usd)

        if tx_type in _IN_TYPES:
            total_in += value
        elif tx_type in _OUT_TYPES:
            total_out += _dec(tx.from_value_usd) or value
        elif tx_type in _INCOME_TYPES:
            total_income += value
        elif tx_type in _EXPENSE_TYPES:
            total_expenses += _dec(tx.from_value_usd) or value
        elif tx_type == "trade":
            # Trades count to both in and out
            total_in += _dec(tx.to_value_usd) or _ZERO
            total_out += _dec(tx.from_value_usd) or _ZERO

        # Fees
        fee = _dec(tx.fee_value_usd)
        total_fees += fee

    # Realized gains from lot assignments in the period
    realized = (
        db.query(func.coalesce(func.sum(LotAssignment.gain_loss_usd), "0"))
        .join(Transaction, LotAssignment.disposal_tx_id == Transaction.id)
        .filter(
            Transaction.datetime_utc >= start_dt,
            Transaction.datetime_utc <= end_dt,
        )
        .scalar()
    )

    return PortfolioStatsResponse(
        total_in=str(total_in.quantize(TWO_PLACES, ROUND_HALF_UP)),
        total_out=str(total_out.quantize(TWO_PLACES, ROUND_HALF_UP)),
        total_income=str(total_income.quantize(TWO_PLACES, ROUND_HALF_UP)),
        total_expenses=str(total_expenses.quantize(TWO_PLACES, ROUND_HALF_UP)),
        total_fees=str(total_fees.quantize(TWO_PLACES, ROUND_HALF_UP)),
        realized_gains=str(_dec(str(realized)).quantize(TWO_PLACES, ROUND_HALF_UP)),
    )
