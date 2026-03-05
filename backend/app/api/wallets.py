import logging

from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, case, or_, and_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Account, Wallet, TaxLot, Asset, Transaction, WalletCostBasisMethod, PriceHistory
from app.services.holdings import compute_balances, compute_cost_basis
from app.schemas.account import AccountResponse
from app.schemas.wallet import (
    CostBasisMethodUpdate,
    TransactionSummary,
    WalletBalanceItem,
    WalletCreate,
    WalletDetailResponse,
    WalletListItemResponse,
    WalletResponse,
    WalletUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


CATEGORY_MAP = {"exchange": "exchange"}


def _derive_category(wallet_type: str) -> str:
    return CATEGORY_MAP.get(wallet_type, "wallet")


def _get_wallet_or_404(wallet_id: int, db: Session) -> Wallet:
    wallet = db.get(Wallet, wallet_id)
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return wallet


@router.get("", response_model=list[WalletListItemResponse])
def list_wallets(
    search: str | None = None,
    sort_by: str = "name",
    sort_dir: str = "asc",
    include_archived: bool = False,
    db: Session = Depends(get_db),
):
    query = db.query(Wallet)

    if not include_archived:
        query = query.filter(Wallet.is_archived == False)

    if search:
        query = query.filter(Wallet.name.ilike(f"%{search}%"))

    # Sorting
    sort_column = {
        "name": Wallet.name,
        "created_at": Wallet.created_at,
        "type": Wallet.type,
    }.get(sort_by, Wallet.name)

    if sort_dir == "desc":
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    wallets = query.all()

    # Pre-fetch latest prices for all assets to avoid N+1 queries
    latest_date_sq = (
        db.query(
            PriceHistory.asset_id,
            func.max(PriceHistory.date).label("max_date"),
        )
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
    all_latest_prices: dict[int, Decimal] = {}
    for lp in latest_prices_rows:
        if lp.asset_id not in all_latest_prices:
            all_latest_prices[lp.asset_id] = Decimal(str(lp.price_usd))

    # Transaction-based balances and cost basis (computed once for all wallets)
    all_balances = compute_balances(db)
    all_cost_basis = compute_cost_basis(db)

    # Build fiat asset ID set for cost basis = face value logic
    fiat_asset_ids = set(
        row[0] for row in db.query(Asset.id).filter(Asset.is_fiat == True).all()
    )

    # Enrich with computed fields
    result = []
    for w in wallets:
        account_count = (
            db.query(func.count(Account.id))
            .filter(Account.wallet_id == w.id, Account.is_archived == False)
            .scalar()
        )

        tx_count = (
            db.query(func.count(Transaction.id))
            .filter(
                or_(
                    Transaction.from_wallet_id == w.id,
                    Transaction.to_wallet_id == w.id,
                )
            )
            .scalar()
        )

        # Slice balances for this wallet from the pre-computed maps
        total_value = Decimal("0")
        total_cost_basis = Decimal("0")
        for (bwid, aid), qty in all_balances.items():
            if bwid != w.id:
                continue
            if aid in fiat_asset_ids:
                cost = qty  # fiat cost basis = face value
            else:
                cost = all_cost_basis.get((bwid, aid), Decimal("0"))
            total_cost_basis += cost
            price = all_latest_prices.get(aid)
            if price is not None and qty > 0:
                total_value += qty * price
            else:
                total_value += cost

        item = WalletListItemResponse(
            **{c.name: getattr(w, c.name) for c in w.__table__.columns},
            account_count=account_count,
            transaction_count=tx_count,
            total_value_usd=str(total_value.quantize(Decimal("0.01"), ROUND_HALF_UP)),
            total_cost_basis_usd=str(total_cost_basis.quantize(Decimal("0.01"), ROUND_HALF_UP)),
        )
        result.append(item)

    return result


@router.post("", response_model=WalletResponse, status_code=201)
def create_wallet(data: WalletCreate, db: Session = Depends(get_db)):
    category = _derive_category(data.type)
    wallet = Wallet(**data.model_dump(), category=category)
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return wallet


@router.get("/{wallet_id}", response_model=WalletDetailResponse)
def get_wallet(wallet_id: int, db: Session = Depends(get_db)):
    wallet = _get_wallet_or_404(wallet_id, db)

    # Transaction-based balances for this wallet
    wallet_balances = compute_balances(db, wallet_id=wallet_id)
    wallet_cost_basis = compute_cost_basis(db, wallet_id=wallet_id)

    # Build fiat asset ID set and asset symbol lookup
    asset_ids_in_use = list({aid for _, aid in wallet_balances})
    asset_map: dict[int, Asset] = {}
    fiat_asset_ids: set[int] = set()
    if asset_ids_in_use:
        for a in db.query(Asset).filter(Asset.id.in_(asset_ids_in_use)).all():
            asset_map[a.id] = a
            if a.is_fiat:
                fiat_asset_ids.add(a.id)

    class _BalRow:
        def __init__(self, asset_id, symbol, quantity, cost_basis):
            self.asset_id = asset_id
            self.symbol = symbol
            self.quantity = quantity
            self.cost_basis = cost_basis

    rows = []
    for (wid, aid), qty in wallet_balances.items():
        asset = asset_map.get(aid)
        if not asset:
            continue
        if aid in fiat_asset_ids:
            cost = qty  # fiat cost basis = face value
        else:
            cost = wallet_cost_basis.get((wid, aid), Decimal("0"))
        rows.append(_BalRow(aid, asset.symbol, qty, cost))

    # Get latest price for each asset
    asset_ids = [r.asset_id for r in rows]
    latest_price: dict[int, Decimal] = {}
    if asset_ids:
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
        for lp in latest_prices_rows:
            if lp.asset_id not in latest_price:
                latest_price[lp.asset_id] = Decimal(str(lp.price_usd))

    TWO_PLACES = Decimal("0.01")

    balances = []
    for r in rows:
        qty = Decimal(str(r.quantity or "0"))
        cost = Decimal(str(r.cost_basis or "0"))
        price = latest_price.get(r.asset_id)

        current_price_usd = None
        market_value_usd = None
        roi_pct = None

        if price is not None and qty > 0:
            market_val = qty * price
            current_price_usd = str(price.quantize(TWO_PLACES, ROUND_HALF_UP))
            market_value_usd = str(market_val.quantize(TWO_PLACES, ROUND_HALF_UP))
            if cost != 0:
                roi = ((market_val - cost) / cost * Decimal("100")).quantize(TWO_PLACES, ROUND_HALF_UP)
                roi_pct = str(roi)

        balances.append(
            WalletBalanceItem(
                asset_id=r.asset_id,
                symbol=r.symbol,
                quantity=str(qty),
                cost_basis_usd=str(cost),
                current_price_usd=current_price_usd,
                market_value_usd=market_value_usd,
                roi_pct=roi_pct,
            )
        )

    # Get accounts for all wallets
    accts = (
        db.query(Account)
        .filter(Account.wallet_id == wallet_id, Account.is_archived == False)
        .order_by(Account.name)
        .all()
    )
    accounts_list = [AccountResponse.model_validate(a) for a in accts]

    # Transaction summary
    tx_counts = (
        db.query(
            Transaction.type,
            func.count(Transaction.id).label("cnt"),
        )
        .filter(
            or_(
                Transaction.from_wallet_id == wallet_id,
                Transaction.to_wallet_id == wallet_id,
            )
        )
        .group_by(Transaction.type)
        .all()
    )

    summary = TransactionSummary()
    type_map = {
        "deposit": "deposits",
        "withdrawal": "withdrawals",
        "trade": "trades",
        "transfer": "transfers",
        "buy": "buys",
        "sell": "sells",
    }
    for row in tx_counts:
        count = row.cnt
        summary.total += count
        attr = type_map.get(row.type)
        if attr:
            setattr(summary, attr, getattr(summary, attr) + count)
        else:
            summary.other += count

    # Exchange connection status
    has_connection = False
    exchange_synced_at = None
    if wallet.category == "exchange":
        try:
            from app.models.exchange_connection import ExchangeConnection
            conn = (
                db.query(ExchangeConnection)
                .filter(ExchangeConnection.wallet_id == wallet_id)
                .first()
            )
            if conn:
                has_connection = True
                exchange_synced_at = conn.last_synced_at
        except Exception:
            pass  # ExchangeConnection model not yet created

    return WalletDetailResponse(
        **{c.name: getattr(wallet, c.name) for c in wallet.__table__.columns},
        balances=balances,
        accounts=accounts_list,
        transaction_summary=summary,
        has_exchange_connection=has_connection,
        exchange_last_synced_at=exchange_synced_at,
    )


@router.put("/{wallet_id}", response_model=WalletResponse)
def update_wallet(wallet_id: int, data: WalletUpdate, db: Session = Depends(get_db)):
    wallet = _get_wallet_or_404(wallet_id, db)
    update_data = data.model_dump(exclude_unset=True)

    # If type changes, re-derive category
    if "type" in update_data:
        update_data["category"] = _derive_category(update_data["type"])

    for field, value in update_data.items():
        setattr(wallet, field, value)
    db.commit()
    db.refresh(wallet)
    return wallet


@router.delete("/{wallet_id}")
def delete_wallet(wallet_id: int, db: Session = Depends(get_db)):
    wallet = _get_wallet_or_404(wallet_id, db)
    db.delete(wallet)
    db.commit()
    return {"detail": "Wallet deleted"}


@router.put("/{wallet_id}/cost-basis-method")
def set_cost_basis_method(
    wallet_id: int,
    data: CostBasisMethodUpdate,
    db: Session = Depends(get_db),
):
    _get_wallet_or_404(wallet_id, db)
    existing = (
        db.query(WalletCostBasisMethod)
        .filter_by(wallet_id=wallet_id, tax_year=data.tax_year)
        .first()
    )
    if existing:
        existing.cost_basis_method = data.cost_basis_method
    else:
        db.add(WalletCostBasisMethod(
            wallet_id=wallet_id,
            tax_year=data.tax_year,
            cost_basis_method=data.cost_basis_method,
        ))
    db.commit()
    return {"detail": "Cost basis method updated"}
