"""Gain/loss computation, holding period, acquisition and disposal processing."""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models import Transaction, TaxLot, LotAssignment, TransactionType, HoldingPeriod
from app.services.lot_selector import get_lot_selector, InsufficientLotsError
from app.services.tax.lot_manager import create_lot, get_open_lots, source_type_for_tx
from app.utils.decimal_helpers import ZERO, PENNY, to_decimal as _to_dec


def resolve_value_usd(primary: str | None, fallback: str | None) -> Decimal:
    """Return the first non-None value as Decimal, falling back to 0."""
    if primary is not None:
        return Decimal(primary)
    if fallback is not None:
        return Decimal(fallback)
    return ZERO


def holding_period(acquired: datetime, disposed: datetime, threshold_days: int = 365) -> str:
    """Determine short-term or long-term based on holding duration."""
    delta = (disposed - acquired).days
    if delta > threshold_days:
        return HoldingPeriod.long_term.value
    return HoldingPeriod.short_term.value


def process_acquisition(
    db: Session, tx: Transaction, wallet_id: int, asset_id: int,
    amount: Decimal, value_usd: Decimal,
):
    """Handle an acquisition: create a new tax lot."""
    fee_usd = ZERO
    if tx.fee_value_usd and tx.type == TransactionType.buy.value:
        fee_usd = _to_dec(tx.fee_value_usd)

    cost_basis = value_usd + fee_usd
    create_lot(
        db,
        wallet_id=wallet_id,
        asset_id=asset_id,
        amount=amount,
        cost_basis_usd=cost_basis,
        acquired_date=tx.datetime_utc,
        acquisition_tx_id=tx.id,
        source_type=source_type_for_tx(tx.type),
    )


def process_disposal(
    db: Session,
    tx: Transaction,
    wallet_id: int,
    asset_id: int,
    amount: Decimal,
    proceeds_usd: Decimal,
    method: str,
    tax_year: int,
) -> list[LotAssignment]:
    """Handle a disposal: select lots, create assignments, calculate gains."""
    fee_usd = ZERO
    if tx.fee_value_usd and tx.type in (TransactionType.sell.value, TransactionType.cost.value):
        fee_usd = _to_dec(tx.fee_value_usd)

    net_proceeds = proceeds_usd - fee_usd

    open_lots = get_open_lots(db, wallet_id, asset_id)
    open_lots = [lot for lot in open_lots if lot.acquired_date <= tx.datetime_utc]
    if not open_lots:
        raise InsufficientLotsError(
            asset_id=asset_id, wallet_id=wallet_id,
            needed=amount, available=ZERO,
        )

    selector = get_lot_selector(method)
    consumptions = selector(open_lots, amount)

    total_consumed = sum(c.amount for c in consumptions)
    assignments = []

    for consumption in consumptions:
        proportion = consumption.amount / total_consumed
        lot_proceeds = (net_proceeds * proportion).quantize(PENNY, rounding=ROUND_HALF_UP)
        lot_basis = consumption.cost_basis_usd
        gain_loss = lot_proceeds - lot_basis

        assignment = LotAssignment(
            disposal_tx_id=tx.id,
            tax_lot_id=consumption.lot.id,
            amount=str(consumption.amount),
            cost_basis_usd=str(lot_basis),
            proceeds_usd=str(lot_proceeds),
            gain_loss_usd=str(gain_loss.quantize(PENNY, rounding=ROUND_HALF_UP)),
            holding_period=holding_period(consumption.lot.acquired_date, tx.datetime_utc),
            cost_basis_method=method,
            tax_year=tax_year,
        )
        db.add(assignment)
        assignments.append(assignment)

        new_remaining = Decimal(consumption.lot.remaining_amount) - consumption.amount
        consumption.lot.remaining_amount = str(new_remaining)
        if new_remaining <= ZERO:
            consumption.lot.is_fully_disposed = True

    db.flush()
    return assignments
