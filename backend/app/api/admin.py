from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Account,
    ExchangeConnection,
    ImportLog,
    LotAssignment,
    TaxLot,
    Transaction,
    Wallet,
    WalletCostBasisMethod,
)

router = APIRouter()


@router.post("/reset-database")
def reset_database(db: Session = Depends(get_db)):
    """Delete all imported data so the user can start fresh.

    Deletes in FK-safe order: lot_assignments, tax_lots, transactions,
    exchange_connections, wallet_cost_basis_methods, accounts, import_logs, wallets.
    """
    db.query(LotAssignment).delete()
    db.query(TaxLot).delete()
    db.query(Transaction).delete()
    db.query(ExchangeConnection).delete()
    db.query(WalletCostBasisMethod).delete()
    db.query(Account).delete()
    db.query(ImportLog).delete()
    db.query(Wallet).delete()
    db.commit()
    return {"detail": "All data has been reset."}


@router.post("/clear-transactions")
def clear_transactions(db: Session = Depends(get_db)):
    """Delete only transactions and related tax data, preserving wallets and accounts."""
    db.query(LotAssignment).delete()
    db.query(TaxLot).delete()
    db.query(Transaction).delete()
    db.query(ImportLog).delete()
    db.commit()
    return {"detail": "Transactions, tax lots, and import logs cleared."}
