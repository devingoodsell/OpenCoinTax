"""Transaction-based holdings computation.

Quantities always derived from transaction history (inflows minus outflows).
Cost basis from open tax lots when available, falling back to zero.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Asset, TaxLot, Transaction

_ZERO = Decimal("0")


def compute_balances(
    db: Session,
    wallet_id: int | None = None,
    exclude_hidden: bool = True,
) -> dict[tuple[int, int], Decimal]:
    """Compute net balances from transaction inflows minus outflows.

    Returns {(wallet_id, asset_id): Decimal} for all pairs with non-zero balance.
    """
    # Build optional filters
    hidden_asset_ids: set[int] = set()
    if exclude_hidden:
        hidden_asset_ids = set(
            row[0] for row in db.query(Asset.id).filter(Asset.is_hidden == True).all()
        )

    # --- inflows: SUM(to_amount) grouped by (to_wallet_id, to_asset_id) ---
    inflow_q = (
        db.query(
            Transaction.to_wallet_id,
            Transaction.to_asset_id,
            func.sum(Transaction.to_amount).label("total"),
        )
        .filter(
            Transaction.to_wallet_id.isnot(None),
            Transaction.to_asset_id.isnot(None),
            Transaction.to_amount.isnot(None),
        )
    )
    if wallet_id is not None:
        inflow_q = inflow_q.filter(Transaction.to_wallet_id == wallet_id)
    inflow_q = inflow_q.group_by(Transaction.to_wallet_id, Transaction.to_asset_id)

    # --- outflows: SUM(from_amount) grouped by (from_wallet_id, from_asset_id) ---
    outflow_q = (
        db.query(
            Transaction.from_wallet_id,
            Transaction.from_asset_id,
            func.sum(Transaction.from_amount).label("total"),
        )
        .filter(
            Transaction.from_wallet_id.isnot(None),
            Transaction.from_asset_id.isnot(None),
            Transaction.from_amount.isnot(None),
        )
    )
    if wallet_id is not None:
        outflow_q = outflow_q.filter(Transaction.from_wallet_id == wallet_id)
    outflow_q = outflow_q.group_by(Transaction.from_wallet_id, Transaction.from_asset_id)

    balances: dict[tuple[int, int], Decimal] = {}

    for row in inflow_q.all():
        key = (row.to_wallet_id, row.to_asset_id)
        if exclude_hidden and row.to_asset_id in hidden_asset_ids:
            continue
        balances[key] = balances.get(key, _ZERO) + Decimal(str(row.total))

    for row in outflow_q.all():
        key = (row.from_wallet_id, row.from_asset_id)
        if exclude_hidden and row.from_asset_id in hidden_asset_ids:
            continue
        balances[key] = balances.get(key, _ZERO) - Decimal(str(row.total))

    # Remove zero/negative balances
    return {k: v for k, v in balances.items() if v > _ZERO}


def compute_cost_basis(
    db: Session,
    wallet_id: int | None = None,
) -> dict[tuple[int, int], Decimal]:
    """Aggregate cost basis from open tax lots: remaining_amount * cost_basis_per_unit.

    Returns {(wallet_id, asset_id): Decimal}. If no lots exist, values are absent.
    Used for display only.
    """
    q = (
        db.query(
            TaxLot.wallet_id,
            TaxLot.asset_id,
            TaxLot.remaining_amount,
            TaxLot.cost_basis_per_unit,
        )
        .filter(TaxLot.is_fully_disposed == False)
    )
    if wallet_id is not None:
        q = q.filter(TaxLot.wallet_id == wallet_id)

    result: dict[tuple[int, int], Decimal] = {}
    for lot in q.all():
        key = (lot.wallet_id, lot.asset_id)
        remaining = Decimal(str(lot.remaining_amount or "0"))
        per_unit = Decimal(str(lot.cost_basis_per_unit or "0"))
        result[key] = result.get(key, _ZERO) + remaining * per_unit

    return result


def compute_balances_before_date(
    db: Session,
    cutoff_date: datetime,
    exclude_hidden: bool = True,
) -> dict[tuple[int, int], Decimal]:
    """Compute net balances from transactions before cutoff_date.

    Same as compute_balances but filtered to datetime_utc < cutoff_date.
    """
    hidden_asset_ids: set[int] = set()
    if exclude_hidden:
        hidden_asset_ids = set(
            row[0] for row in db.query(Asset.id).filter(Asset.is_hidden == True).all()
        )

    inflow_q = (
        db.query(
            Transaction.to_wallet_id,
            Transaction.to_asset_id,
            func.sum(Transaction.to_amount).label("total"),
        )
        .filter(
            Transaction.to_wallet_id.isnot(None),
            Transaction.to_asset_id.isnot(None),
            Transaction.to_amount.isnot(None),
            Transaction.datetime_utc < cutoff_date,
        )
        .group_by(Transaction.to_wallet_id, Transaction.to_asset_id)
    )

    outflow_q = (
        db.query(
            Transaction.from_wallet_id,
            Transaction.from_asset_id,
            func.sum(Transaction.from_amount).label("total"),
        )
        .filter(
            Transaction.from_wallet_id.isnot(None),
            Transaction.from_asset_id.isnot(None),
            Transaction.from_amount.isnot(None),
            Transaction.datetime_utc < cutoff_date,
        )
        .group_by(Transaction.from_wallet_id, Transaction.from_asset_id)
    )

    balances: dict[tuple[int, int], Decimal] = {}

    for row in inflow_q.all():
        key = (row.to_wallet_id, row.to_asset_id)
        if exclude_hidden and row.to_asset_id in hidden_asset_ids:
            continue
        balances[key] = balances.get(key, _ZERO) + Decimal(str(row.total))

    for row in outflow_q.all():
        key = (row.from_wallet_id, row.from_asset_id)
        if exclude_hidden and row.from_asset_id in hidden_asset_ids:
            continue
        balances[key] = balances.get(key, _ZERO) - Decimal(str(row.total))

    # Keep zero/negative — caller may need to see them for cost tracking
    return {k: v for k, v in balances.items() if v > _ZERO}
