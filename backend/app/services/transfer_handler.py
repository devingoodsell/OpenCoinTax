"""Transfer handler — propagates cost basis when crypto moves between wallets.

Transfers are non-taxable. Cost basis and acquired_date carry over from
source lots to new lots in the destination wallet.
"""

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models import Transaction, TaxLot, LotAssignment, TransactionType
from app.services.lot_selector import get_lot_selector, LotConsumption
from app.services.tax_engine import _get_open_lots, get_cost_basis_method
from app.utils.decimal_helpers import ZERO, PENNY, to_decimal as _to_dec


def process_transfer(
    db: Session,
    tx: Transaction,
    tax_year: int,
) -> list[TaxLot]:
    """Process a transfer transaction: consume lots in source, create in destination.

    Returns the newly created lots in the destination wallet.
    """
    assert tx.type == TransactionType.transfer.value

    from_wallet_id = tx.from_wallet_id
    to_wallet_id = tx.to_wallet_id
    asset_id = tx.from_asset_id  # same asset on both sides
    amount = _to_dec(tx.from_amount)
    fee_usd = _to_dec(tx.fee_value_usd)

    if not from_wallet_id or not to_wallet_id or not asset_id:
        raise ValueError(f"Transfer tx {tx.id} missing wallet or asset IDs")

    # Get cost basis method for the source wallet
    method = get_cost_basis_method(db, from_wallet_id, tax_year)

    # Select lots from source wallet
    open_lots = _get_open_lots(db, from_wallet_id, asset_id)
    selector = get_lot_selector(method)
    consumptions = selector(open_lots, amount)

    # Distribute transfer fee proportionally if configured to add to basis
    total_consumed = sum(c.amount for c in consumptions)

    # Check for temporary lots created for this transfer during earlier
    # pair processing (when dest wallet was processed before source wallet).
    existing_temp_lots = (
        db.query(TaxLot)
        .filter_by(acquisition_tx_id=tx.id, wallet_id=to_wallet_id)
        .all()
    )

    if existing_temp_lots:
        # Check if any temp lots have been consumed by disposals (have assignments).
        # If so, we can't safely delete them — the disposal already used them.
        temp_lot_ids = [lot.id for lot in existing_temp_lots]
        used_lot_ids = set(
            r[0] for r in db.query(LotAssignment.tax_lot_id)
            .filter(LotAssignment.tax_lot_id.in_(temp_lot_ids))
            .distinct()
            .all()
        )

        # Also check if remaining < amount (partially consumed by withdrawals)
        consumed_lot_ids = used_lot_ids | {
            lot.id for lot in existing_temp_lots
            if Decimal(lot.remaining_amount) < Decimal(lot.amount)
        }

        if consumed_lot_ids:
            # Temp lots have been consumed by disposals.  Source lots are still
            # consumed (above) to keep the source wallet's balance correct.
            # Keep consumed temp lots in dest — delete only safe-to-delete ones.
            safe_to_delete = [lot for lot in existing_temp_lots if lot.id not in consumed_lot_ids]
            for lot in safe_to_delete:
                db.delete(lot)
            if safe_to_delete:
                db.flush()
            # Don't create new lots — the consumed temp lots already represent the transfer
            db.flush()
            return [lot for lot in existing_temp_lots if lot.id in consumed_lot_ids]

        # No temp lots consumed — safe to delete all and recreate with real cost basis
        for temp_lot in existing_temp_lots:
            db.delete(temp_lot)
        db.flush()

    new_lots: list[TaxLot] = []

    for consumption in consumptions:
        # Deduct from source lot
        new_remaining = Decimal(consumption.lot.remaining_amount) - consumption.amount
        consumption.lot.remaining_amount = str(new_remaining)
        if new_remaining <= ZERO:
            consumption.lot.is_fully_disposed = True

        # Carry over original cost basis and acquired date
        per_unit = Decimal(consumption.lot.cost_basis_per_unit)
        carried_basis = consumption.cost_basis_usd

        # Add proportional fee to cost basis
        if fee_usd > ZERO and total_consumed > ZERO:
            proportion = consumption.amount / total_consumed
            fee_portion = (fee_usd * proportion).quantize(PENNY, rounding=ROUND_HALF_UP)
            carried_basis += fee_portion
            # Recalculate per-unit with fee
            per_unit = (carried_basis / consumption.amount).quantize(
                Decimal("0.00000001"), rounding=ROUND_HALF_UP
            )

        new_lot = TaxLot(
            wallet_id=to_wallet_id,
            asset_id=asset_id,
            amount=str(consumption.amount),
            remaining_amount=str(consumption.amount),
            cost_basis_usd=str(carried_basis.quantize(PENNY, rounding=ROUND_HALF_UP)),
            cost_basis_per_unit=str(per_unit),
            acquired_date=consumption.lot.acquired_date,  # preserve original date
            acquisition_tx_id=tx.id,
            source_type="transfer_in",
        )
        db.add(new_lot)
        new_lots.append(new_lot)

    db.flush()
    return new_lots
