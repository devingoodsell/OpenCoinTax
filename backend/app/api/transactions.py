from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset, Transaction, LotAssignment, TaxLot
from app.schemas.transaction import (
    LotAssignmentResponse,
    TransactionCreate,
    TransactionDetailResponse,
    TransactionListResponse,
    TransactionResponse,
    TransactionUpdate,
)


def _enrich_tx(tx: Transaction) -> dict:
    """Build a dict from a Transaction ORM object with resolved relationship names."""
    data = {c.name: getattr(tx, c.name) for c in tx.__table__.columns}
    data["from_wallet_name"] = tx.from_wallet.name if tx.from_wallet else None
    data["to_wallet_name"] = tx.to_wallet.name if tx.to_wallet else None
    data["from_account_name"] = tx.from_account.name if tx.from_account else None
    data["to_account_name"] = tx.to_account.name if tx.to_account else None
    data["from_asset_symbol"] = tx.from_asset.symbol if tx.from_asset else None
    data["to_asset_symbol"] = tx.to_asset.symbol if tx.to_asset else None
    data["fee_asset_symbol"] = tx.fee_asset.symbol if tx.fee_asset else None
    return data

router = APIRouter()


@router.get("/error-count")
def transaction_error_count(db: Session = Depends(get_db)):
    """Return the count of transactions with tax errors."""
    count = db.query(func.count(Transaction.id)).filter(
        Transaction.has_tax_error == True
    ).scalar()
    return {"error_count": count}


@router.get("", response_model=TransactionListResponse)
def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    wallet_id: int | None = None,
    account_id: int | None = None,
    asset_id: int | None = None,
    asset_symbol: str | None = None,
    type: str | None = None,
    exclude_types: str | None = Query(None, description="Comma-separated types to exclude"),
    label: str | None = None,
    search: str | None = None,
    has_errors: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Transaction)

    if has_errors is not None:
        q = q.filter(Transaction.has_tax_error == has_errors)
    if wallet_id is not None:
        q = q.filter(
            or_(
                Transaction.from_wallet_id == wallet_id,
                Transaction.to_wallet_id == wallet_id,
            )
        )
    if account_id is not None:
        q = q.filter(
            or_(
                Transaction.from_account_id == account_id,
                Transaction.to_account_id == account_id,
            )
        )
    if asset_id is not None:
        q = q.filter(
            or_(
                Transaction.from_asset_id == asset_id,
                Transaction.to_asset_id == asset_id,
            )
        )
    if asset_symbol is not None:
        matching_ids = (
            db.query(Asset.id)
            .filter(Asset.symbol.ilike(f"%{asset_symbol}%"))
            .all()
        )
        ids = [row.id for row in matching_ids]
        if ids:
            q = q.filter(
                or_(
                    Transaction.from_asset_id.in_(ids),
                    Transaction.to_asset_id.in_(ids),
                )
            )
        else:
            q = q.filter(False)  # no matches → empty result
    if type is not None:
        q = q.filter(Transaction.type == type)
    if exclude_types is not None:
        excluded = [t.strip() for t in exclude_types.split(",") if t.strip()]
        if excluded:
            q = q.filter(Transaction.type.notin_(excluded))
    if label is not None:
        q = q.filter(Transaction.label == label)
    if search:
        q = q.filter(
            Transaction.tx_hash.contains(search)
            | Transaction.description.contains(search)
        )
    if date_from is not None:
        q = q.filter(Transaction.datetime_utc >= datetime.combine(date_from, datetime.min.time()))
    if date_to is not None:
        q = q.filter(Transaction.datetime_utc <= datetime.combine(date_to, datetime.max.time()))

    total = q.count()
    items = (
        q.order_by(Transaction.datetime_utc.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return TransactionListResponse(
        items=[TransactionResponse(**_enrich_tx(t)) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=TransactionResponse, status_code=201)
def create_transaction(data: TransactionCreate, db: Session = Depends(get_db)):
    tx = Transaction(**data.model_dump())
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx


@router.get("/{tx_id}", response_model=TransactionDetailResponse)
def get_transaction(tx_id: int, db: Session = Depends(get_db)):
    tx = db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    assignments = db.query(LotAssignment).filter_by(disposal_tx_id=tx_id).all()
    lot_responses = []
    for a in assignments:
        lot = db.get(TaxLot, a.tax_lot_id)
        lot_responses.append(
            LotAssignmentResponse(
                id=a.id,
                tax_lot_id=a.tax_lot_id,
                amount=a.amount,
                cost_basis_usd=a.cost_basis_usd,
                proceeds_usd=a.proceeds_usd,
                gain_loss_usd=a.gain_loss_usd,
                holding_period=a.holding_period,
                cost_basis_method=a.cost_basis_method,
                acquired_date=lot.acquired_date if lot else None,
            )
        )

    return TransactionDetailResponse(
        **_enrich_tx(tx),
        lot_assignments=lot_responses,
    )


@router.put("/{tx_id}", response_model=TransactionResponse)
def update_transaction(
    tx_id: int, data: TransactionUpdate, db: Session = Depends(get_db)
):
    tx = db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(tx, field, value)
    # Clear tax error flags when user edits
    tx.tax_error = None
    tx.has_tax_error = False
    db.commit()
    db.refresh(tx)
    return TransactionResponse(**_enrich_tx(tx))


@router.delete("/{tx_id}")
def delete_transaction(tx_id: int, db: Session = Depends(get_db)):
    tx = db.get(Transaction, tx_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    db.delete(tx)
    db.commit()
    return {"detail": "Transaction deleted"}
