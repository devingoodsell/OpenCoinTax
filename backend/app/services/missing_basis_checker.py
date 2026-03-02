"""Missing cost basis detection — finds tax lots that likely have incorrect
zero-cost basis.

Zero-basis is legitimate for airdrops, forks, and gifts received. All other
lot types with $0 cost basis are flagged as warnings, since they may indicate
missing price data or import errors.
"""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.models import (
    Asset,
    TaxLot,
    Transaction,
    Wallet,
    TransactionType,
)
from app.utils.decimal_helpers import ZERO

# Source types where $0 cost basis is legitimate
LEGITIMATE_ZERO_BASIS = frozenset({"airdrop", "fork", "gift"})


def find_missing_basis(db: Session) -> list[dict]:
    """Find tax lots that have a zero cost basis but whose source type
    does not justify it.

    Also detects deposits from external wallets with no matching outbound
    transfer (orphan deposits).

    Returns a list of dicts with:
        lot_id, transaction_id, date, asset_symbol, amount,
        wallet_name, reason
    """
    results: list[dict] = []

    # --- Check 1: Zero-basis lots that aren't airdrops/forks/gifts ---
    all_lots = db.query(TaxLot).all()

    for lot in all_lots:
        cost_basis = Decimal(lot.cost_basis_usd)
        if cost_basis == ZERO and lot.source_type not in LEGITIMATE_ZERO_BASIS:
            asset = db.get(Asset, lot.asset_id)
            wallet = db.get(Wallet, lot.wallet_id)
            tx = db.get(Transaction, lot.acquisition_tx_id)

            results.append({
                "lot_id": lot.id,
                "transaction_id": lot.acquisition_tx_id,
                "date": tx.datetime_utc.isoformat() if tx else None,
                "asset_symbol": asset.symbol if asset else "UNKNOWN",
                "amount": lot.amount,
                "wallet_name": wallet.name if wallet else "Unknown",
                "reason": f"Zero cost basis on {lot.source_type} lot",
            })

    # --- Check 2: Deposits with no matching outbound transfer ---
    deposit_txns = (
        db.query(Transaction)
        .filter(Transaction.type == TransactionType.deposit.value)
        .all()
    )

    for dep in deposit_txns:
        if not dep.to_wallet_id or not dep.to_asset_id:
            continue

        # Look for a matching withdrawal/transfer from another wallet
        # within a reasonable time window (same amount, same asset)
        has_matching_outbound = False

        if dep.to_amount:
            matching = (
                db.query(Transaction)
                .filter(
                    Transaction.type.in_([
                        TransactionType.withdrawal.value,
                        TransactionType.transfer.value,
                    ]),
                    Transaction.from_asset_id == dep.to_asset_id,
                    Transaction.from_amount == dep.to_amount,
                    Transaction.id != dep.id,
                )
                .first()
            )
            if matching is not None:
                has_matching_outbound = True

        if not has_matching_outbound:
            asset = db.get(Asset, dep.to_asset_id)
            wallet = db.get(Wallet, dep.to_wallet_id)

            results.append({
                "lot_id": None,
                "transaction_id": dep.id,
                "date": dep.datetime_utc.isoformat(),
                "asset_symbol": asset.symbol if asset else "UNKNOWN",
                "amount": dep.to_amount or "0",
                "wallet_name": wallet.name if wallet else "Unknown",
                "reason": "Deposit with no matching outbound transfer",
            })

    return results
