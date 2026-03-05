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
    STABLECOIN_SYMBOLS,
    TaxLot,
    Transaction,
    Wallet,
)
from app.services.holdings import compute_balances, compute_cost_basis, compute_balances_before_date

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
_STABLECOIN_SYMBOLS = STABLECOIN_SYMBOLS | {"USD"}


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

    Quantities are derived from transaction history (event-based).
    For each day, sums (balance × price) for all assets held.
    """

    start_dt = datetime.combine(start_date, datetime.min.time())

    # 1. Get initial balances before start_date from transactions
    #    {(wallet_id, asset_id): Decimal}
    initial_balances = compute_balances_before_date(db, start_dt)

    # 2. Get all transactions in [start_date, end_date] to track balance changes
    end_dt = datetime.combine(end_date, datetime.max.time())
    txs_in_range = (
        db.query(Transaction)
        .filter(
            Transaction.datetime_utc >= start_dt,
            Transaction.datetime_utc <= end_dt,
        )
        .order_by(Transaction.datetime_utc)
        .all()
    )

    # Collect all asset IDs involved (from initial + transactions)
    all_asset_ids: set[int] = set()
    for _, aid in initial_balances:
        all_asset_ids.add(aid)
    for tx in txs_in_range:
        if tx.to_asset_id:
            all_asset_ids.add(tx.to_asset_id)
        if tx.from_asset_id:
            all_asset_ids.add(tx.from_asset_id)

    # Filter out hidden assets
    hidden_asset_ids = set(
        row[0] for row in db.query(Asset.id).filter(Asset.is_hidden == True).all()
    )
    all_asset_ids -= hidden_asset_ids

    if not all_asset_ids and not initial_balances:
        return DailyValuesResponse(
            data_points=[],
            summary=DailyValuesSummary(
                current_value="0.00",
                total_cost_basis="0.00",
                unrealized_gain="0.00",
                unrealized_gain_pct="0.00",
            ),
        )

    asset_ids = list(all_asset_ids)

    # Identify stablecoin assets — always priced at $1.00
    stablecoin_asset_ids = set(
        row[0] for row in db.query(Asset.id)
        .filter(Asset.id.in_(asset_ids), Asset.symbol.in_(_STABLECOIN_SYMBOLS))
        .all()
    ) if asset_ids else set()

    # 3. Fetch price data
    price_map: dict[tuple[int, date], Decimal] = {}
    if asset_ids:
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
        for p in prices:
            key = (p.asset_id, p.date)
            if key not in price_map:
                price_map[key] = _dec(p.price_usd)

    # Fetch prices just before the range for forward-fill
    last_known_before: dict[int, Decimal] = {}
    if asset_ids:
        pre_prices = (
            db.query(PriceHistory.asset_id, PriceHistory.date, PriceHistory.price_usd)
            .filter(
                PriceHistory.asset_id.in_(asset_ids),
                PriceHistory.date < start_date,
            )
            .order_by(PriceHistory.asset_id, PriceHistory.date.desc())
            .all()
        )
        for p in pre_prices:
            if p.asset_id not in last_known_before:
                last_known_before[p.asset_id] = _dec(p.price_usd)

    # 4. Build balance-change events from transactions
    #    Each event: (date, asset_id, delta) — aggregated per asset (ignoring wallet)
    balance_events: dict[date, dict[int, Decimal]] = {}
    # Also track running cost basis changes from to_value_usd / from_value_usd
    cost_events: dict[date, dict[int, Decimal]] = {}

    for tx in txs_in_range:
        tx_date = tx.datetime_utc.date() if isinstance(tx.datetime_utc, datetime) else tx.datetime_utc
        # Inflow
        if tx.to_asset_id and tx.to_amount and tx.to_asset_id not in hidden_asset_ids:
            if tx_date not in balance_events:
                balance_events[tx_date] = {}
            balance_events[tx_date][tx.to_asset_id] = (
                balance_events[tx_date].get(tx.to_asset_id, _ZERO) + _dec(tx.to_amount)
            )
            # Cost tracking: acquisition adds cost
            if tx.to_value_usd:
                if tx_date not in cost_events:
                    cost_events[tx_date] = {}
                cost_events[tx_date][tx.to_asset_id] = (
                    cost_events[tx_date].get(tx.to_asset_id, _ZERO) + _dec(tx.to_value_usd)
                )
        # Outflow
        if tx.from_asset_id and tx.from_amount and tx.from_asset_id not in hidden_asset_ids:
            if tx_date not in balance_events:
                balance_events[tx_date] = {}
            balance_events[tx_date][tx.from_asset_id] = (
                balance_events[tx_date].get(tx.from_asset_id, _ZERO) - _dec(tx.from_amount)
            )
            # Cost tracking: disposal reduces cost proportionally
            if tx.from_value_usd:
                if tx_date not in cost_events:
                    cost_events[tx_date] = {}
                cost_events[tx_date][tx.from_asset_id] = (
                    cost_events[tx_date].get(tx.from_asset_id, _ZERO) - _dec(tx.from_value_usd)
                )

    # 5. Compute initial cost basis from open lots before start_date
    #    Aggregate per asset (across wallets) for the initial snapshot
    initial_cost_per_asset: dict[int, Decimal] = {}
    pre_lots = (
        db.query(
            TaxLot.asset_id,
            TaxLot.remaining_amount,
            TaxLot.cost_basis_per_unit,
        )
        .filter(TaxLot.is_fully_disposed == False)
        .all()
    )
    for lot in pre_lots:
        aid = lot.asset_id
        if aid in hidden_asset_ids:
            continue
        remaining = _dec(lot.remaining_amount)
        per_unit = _dec(lot.cost_basis_per_unit)
        initial_cost_per_asset[aid] = initial_cost_per_asset.get(aid, _ZERO) + remaining * per_unit

    # 6. Collapse initial_balances by asset (sum across wallets)
    running_balance: dict[int, Decimal] = {}
    for (_, aid), qty in initial_balances.items():
        if aid in hidden_asset_ids:
            continue
        running_balance[aid] = running_balance.get(aid, _ZERO) + qty

    running_cost: dict[int, Decimal] = dict(initial_cost_per_asset)

    # 7. Build sample dates
    total_days = (end_date - start_date).days + 1
    max_points = 300
    step = max(1, total_days // max_points)

    sample_dates: list[date] = []
    current_day = start_date
    while current_day <= end_date:
        sample_dates.append(current_day)
        current_day += timedelta(days=step)
    if sample_dates[-1] != end_date:
        sample_dates.append(end_date)

    # 8. Walk day-by-day with forward-fill pricing
    data_points: list[DailyDataPoint] = []
    last_price: dict[int, Decimal] = dict(last_known_before)
    for aid in stablecoin_asset_ids:
        last_price[aid] = _ONE
    sample_set = set(sample_dates)

    walk_day = start_date
    while walk_day <= end_date:
        # Apply balance/cost events for this day
        if walk_day in balance_events:
            for aid, delta in balance_events[walk_day].items():
                running_balance[aid] = running_balance.get(aid, _ZERO) + delta
        if walk_day in cost_events:
            for aid, delta in cost_events[walk_day].items():
                running_cost[aid] = running_cost.get(aid, _ZERO) + delta

        # Update forward-fill prices
        for aid in asset_ids:
            key = (aid, walk_day)
            if key in price_map:
                if aid not in stablecoin_asset_ids:
                    last_price[aid] = price_map[key]

        if walk_day in sample_set:
            day_value = _ZERO
            day_cost_basis = _ZERO

            for aid, qty in running_balance.items():
                if qty <= _ZERO:
                    continue
                price = last_price.get(aid, _ZERO)
                day_value += qty * price
                # Use running cost if available, else zero
                asset_cost = running_cost.get(aid, _ZERO)
                if asset_cost > _ZERO:
                    day_cost_basis += asset_cost
                else:
                    # Fallback: use price as proxy for cost if no cost data
                    pass

            data_points.append(DailyDataPoint(
                date=walk_day.isoformat(),
                total_value_usd=str(day_value.quantize(TWO_PLACES, ROUND_HALF_UP)),
                cost_basis_usd=str(day_cost_basis.quantize(TWO_PLACES, ROUND_HALF_UP)),
            ))

        walk_day += timedelta(days=1)

    # 9. Summary from the last data point
    if data_points:
        last = data_points[-1]
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
    """Return consolidated holdings aggregated across all wallets.

    Quantities are derived from transaction history (inflows minus outflows).
    Cost basis comes from open tax lots when available; for fiat, cost basis = face value.
    """

    # Transaction-based balances: {(wallet_id, asset_id): qty}
    all_balances = compute_balances(db)
    # Cost basis from open tax lots: {(wallet_id, asset_id): cost}
    all_cost_basis = compute_cost_basis(db)

    if not all_balances:
        return HoldingsResponse(holdings=[], total_portfolio_value="0.00")

    # Look up asset metadata
    asset_ids_in_use = list({aid for _, aid in all_balances})
    asset_map: dict[int, Asset] = {
        a.id: a for a in db.query(Asset).filter(Asset.id.in_(asset_ids_in_use)).all()
    }
    wallet_ids_in_use = list({wid for wid, _ in all_balances})
    wallet_map: dict[int, Wallet] = {
        w.id: w for w in db.query(Wallet).filter(Wallet.id.in_(wallet_ids_in_use)).all()
    }

    # Aggregate by asset_id across wallets
    agg: dict[int, dict] = {}
    wallet_agg: dict[int, dict[int, dict]] = {}  # asset_id -> wallet_id -> {name, qty}
    for (wid, aid), qty in all_balances.items():
        asset = asset_map.get(aid)
        if not asset:
            continue
        if aid not in agg:
            agg[aid] = {
                "symbol": asset.symbol,
                "asset_name": asset.name,
                "total_qty": _ZERO,
                "total_cost": _ZERO,
                "is_fiat": asset.is_fiat,
            }
        agg[aid]["total_qty"] += qty
        # Cost basis: from lots, or face value for fiat
        lot_cost = all_cost_basis.get((wid, aid), _ZERO)
        if asset.is_fiat:
            agg[aid]["total_cost"] += qty  # fiat cost basis = face value
        else:
            agg[aid]["total_cost"] += lot_cost

        # Per-wallet breakdown
        if aid not in wallet_agg:
            wallet_agg[aid] = {}
        wallet = wallet_map.get(wid)
        wallet_name = wallet.name if wallet else "Unknown"
        if wid not in wallet_agg[aid]:
            wallet_agg[aid][wid] = {"name": wallet_name, "qty": _ZERO}
        wallet_agg[aid][wid]["qty"] += qty

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
