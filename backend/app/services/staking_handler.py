"""Staking reward handler — creates income events and tax lots for staking rewards.

Each staking reward creates:
1. An income event (ordinary income at FMV when received)
2. A new tax lot with cost_basis = FMV at receipt
"""

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models import Transaction, TaxLot, TransactionType, INCOME_TYPES
from app.utils.decimal_helpers import ZERO, PENNY


def calculate_staking_income(
    db: Session,
    wallet_id: int,
    asset_id: int,
    tax_year: int,
) -> dict:
    """Calculate total staking/income for a (wallet, asset, year).

    Returns summary of income by type.
    """
    from datetime import datetime

    txns = (
        db.query(Transaction)
        .filter(
            Transaction.to_wallet_id == wallet_id,
            Transaction.to_asset_id == asset_id,
            Transaction.type.in_([t.value for t in INCOME_TYPES]),
            Transaction.datetime_utc >= datetime(tax_year, 1, 1),
            Transaction.datetime_utc < datetime(tax_year + 1, 1, 1),
        )
        .order_by(Transaction.datetime_utc)
        .all()
    )

    income_by_type: dict[str, Decimal] = {}

    for tx in txns:
        value = Decimal(tx.to_value_usd) if tx.to_value_usd else ZERO
        income_by_type[tx.type] = income_by_type.get(tx.type, ZERO) + value

    total = sum(income_by_type.values(), ZERO)

    return {
        "wallet_id": wallet_id,
        "asset_id": asset_id,
        "tax_year": tax_year,
        "total_income": str(total.quantize(PENNY, rounding=ROUND_HALF_UP)),
        "staking_income": str(
            income_by_type.get(TransactionType.staking_reward.value, ZERO)
            .quantize(PENNY, rounding=ROUND_HALF_UP)
        ),
        "airdrop_income": str(
            income_by_type.get(TransactionType.airdrop.value, ZERO)
            .quantize(PENNY, rounding=ROUND_HALF_UP)
        ),
        "mining_income": str(
            income_by_type.get(TransactionType.mining.value, ZERO)
            .quantize(PENNY, rounding=ROUND_HALF_UP)
        ),
        "interest_income": str(
            income_by_type.get(TransactionType.interest.value, ZERO)
            .quantize(PENNY, rounding=ROUND_HALF_UP)
        ),
    }
