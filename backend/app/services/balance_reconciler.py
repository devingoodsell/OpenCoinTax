"""Balance reconciliation — compares expected balances from transaction history
against the sum of remaining amounts in open tax lots.

Discrepancies indicate data corruption, missed transactions, or tax engine bugs.
"""

from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Asset,
    TaxLot,
    Transaction,
    Wallet,
    ACQUISITION_TYPES,
    DISPOSAL_TYPES,
    TransactionType,
)
from app.utils.decimal_helpers import ZERO


def reconcile_balances(db: Session) -> list[dict]:
    """For each (wallet_id, asset_id) pair, compare the expected balance
    derived from transaction history against the sum of remaining_amount
    from tax lots.

    Returns a list of dicts with:
        wallet_id, wallet_name, asset_id, asset_symbol,
        expected_balance, lot_balance, difference, is_discrepancy
    """
    # Gather all (wallet_id, asset_id) pairs that have tax lots
    pairs = (
        db.query(TaxLot.wallet_id, TaxLot.asset_id)
        .group_by(TaxLot.wallet_id, TaxLot.asset_id)
        .all()
    )

    results: list[dict] = []

    acquisition_type_values = frozenset(t.value for t in ACQUISITION_TYPES)
    disposal_type_values = frozenset(t.value for t in DISPOSAL_TYPES)
    # trade is both: from-side is disposal, to-side is acquisition
    trade_value = TransactionType.trade.value
    transfer_value = TransactionType.transfer.value

    for wallet_id, asset_id in pairs:
        # ----- Expected balance from transactions -----
        # Inflows: transactions where this wallet/asset appears on the to-side
        inflow = ZERO
        inflow_txns = (
            db.query(Transaction)
            .filter(
                Transaction.to_wallet_id == wallet_id,
                Transaction.to_asset_id == asset_id,
            )
            .all()
        )
        for tx in inflow_txns:
            if tx.to_amount:
                inflow += Decimal(tx.to_amount)

        # Outflows: transactions where this wallet/asset appears on the from-side
        outflow = ZERO
        outflow_txns = (
            db.query(Transaction)
            .filter(
                Transaction.from_wallet_id == wallet_id,
                Transaction.from_asset_id == asset_id,
            )
            .all()
        )
        for tx in outflow_txns:
            if tx.from_amount:
                outflow += Decimal(tx.from_amount)

        expected_balance = inflow - outflow

        # ----- Lot balance from tax lots -----
        lot_sum = (
            db.query(func.sum(TaxLot.remaining_amount))
            .filter(TaxLot.wallet_id == wallet_id, TaxLot.asset_id == asset_id)
            .scalar()
        )
        lot_balance = Decimal(str(lot_sum)) if lot_sum else ZERO

        difference = expected_balance - lot_balance

        # Look up names for readability
        wallet = db.get(Wallet, wallet_id)
        asset = db.get(Asset, asset_id)

        results.append({
            "wallet_id": wallet_id,
            "wallet_name": wallet.name if wallet else "Unknown",
            "asset_id": asset_id,
            "asset_symbol": asset.symbol if asset else "UNKNOWN",
            "expected_balance": str(expected_balance),
            "lot_balance": str(lot_balance),
            "difference": str(difference),
            "is_discrepancy": difference != ZERO,
        })

    return results
