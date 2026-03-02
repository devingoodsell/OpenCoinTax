"""Wrapping swap handler — non-taxable basis carry-over for wrapped asset pairs.

Wrapping swaps (ETH→STETH, ETH→WETH, BTC→WBTC) are treated identically to
transfers: cost basis and acquired_date carry over from the source lots to new
lots in the wrapped asset.  No capital gain or loss is recognised.
"""

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models import (
    Asset, Transaction, TaxLot, LotAssignment, TransactionType, LotSourceType,
    WRAPPING_PAIRS,
)
from app.services.lot_selector import get_lot_selector, LotConsumption
from app.services.tax_engine import _get_open_lots, get_cost_basis_method
from app.utils.decimal_helpers import ZERO, PENNY, to_decimal as _to_dec

# Cache: asset_id -> symbol (populated lazily)
_symbol_cache: dict[int, str] = {}


def _get_symbol(db: Session, asset_id: int) -> str:
    """Return the symbol for an asset_id, using a session-level cache."""
    if asset_id not in _symbol_cache:
        asset = db.get(Asset, asset_id)
        if asset is None:
            return ""
        _symbol_cache[asset_id] = asset.symbol
    return _symbol_cache[asset_id]


def is_wrapping_swap(db: Session, tx: Transaction) -> bool:
    """Return True if *tx* is a trade between a recognised wrapping pair."""
    if tx.type != TransactionType.trade.value:
        return False
    if not tx.from_asset_id or not tx.to_asset_id:
        return False

    from_sym = _get_symbol(db, tx.from_asset_id)
    to_sym = _get_symbol(db, tx.to_asset_id)
    if not from_sym or not to_sym:
        return False

    return frozenset({from_sym, to_sym}) in WRAPPING_PAIRS


def process_wrapping_swap(
    db: Session,
    tx: Transaction,
    tax_year: int,
) -> list[TaxLot]:
    """Consume from-asset lots and create to-asset lots carrying over basis.

    Returns the newly created lots for the to-asset.
    """
    from_wallet_id = tx.from_wallet_id
    to_wallet_id = tx.to_wallet_id
    from_asset_id = tx.from_asset_id
    to_asset_id = tx.to_asset_id
    from_amount = _to_dec(tx.from_amount)
    to_amount = _to_dec(tx.to_amount)

    if not from_wallet_id or not to_wallet_id or not from_asset_id or not to_asset_id:
        raise ValueError(f"Wrapping swap tx {tx.id} missing wallet or asset IDs")

    # Get cost basis method for the source wallet
    method = get_cost_basis_method(db, from_wallet_id, tax_year)

    # Select lots from source (from-asset) wallet
    open_lots = _get_open_lots(db, from_wallet_id, from_asset_id)
    selector = get_lot_selector(method)
    consumptions = selector(open_lots, from_amount)

    total_consumed = sum(c.amount for c in consumptions)

    # --- Handle temp lots (same pattern as transfer_handler) ---
    existing_temp_lots = (
        db.query(TaxLot)
        .filter_by(
            acquisition_tx_id=tx.id,
            wallet_id=to_wallet_id,
            asset_id=to_asset_id,
        )
        .all()
    )

    if existing_temp_lots:
        temp_lot_ids = [lot.id for lot in existing_temp_lots]
        used_lot_ids = set(
            r[0] for r in db.query(LotAssignment.tax_lot_id)
            .filter(LotAssignment.tax_lot_id.in_(temp_lot_ids))
            .distinct()
            .all()
        )
        consumed_lot_ids = used_lot_ids | {
            lot.id for lot in existing_temp_lots
            if Decimal(lot.remaining_amount) < Decimal(lot.amount)
        }

        if consumed_lot_ids:
            # Temp lots already consumed — keep them, consume source lots only
            safe_to_delete = [
                lot for lot in existing_temp_lots
                if lot.id not in consumed_lot_ids
            ]
            for lot in safe_to_delete:
                db.delete(lot)
            if safe_to_delete:
                db.flush()

            # Still consume source lots to keep source balance correct
            for consumption in consumptions:
                new_remaining = Decimal(consumption.lot.remaining_amount) - consumption.amount
                consumption.lot.remaining_amount = str(new_remaining)
                if new_remaining <= ZERO:
                    consumption.lot.is_fully_disposed = True
            db.flush()
            return [lot for lot in existing_temp_lots if lot.id in consumed_lot_ids]

        # No temp lots consumed — delete all and recreate with real cost basis
        for temp_lot in existing_temp_lots:
            db.delete(temp_lot)
        db.flush()

    # --- Create new lots for the to-asset ---
    new_lots: list[TaxLot] = []

    for consumption in consumptions:
        # Deduct from source lot
        new_remaining = Decimal(consumption.lot.remaining_amount) - consumption.amount
        consumption.lot.remaining_amount = str(new_remaining)
        if new_remaining <= ZERO:
            consumption.lot.is_fully_disposed = True

        # Carry over original cost basis and acquired date
        carried_basis = consumption.cost_basis_usd

        # Distribute to_amount proportionally (amounts may differ: 1.9024 ETH → 1.9 STETH)
        proportion = consumption.amount / total_consumed
        lot_to_amount = (to_amount * proportion).quantize(
            Decimal("0.000000000000000001"), rounding=ROUND_HALF_UP
        )

        # Recalculate per-unit for the new asset
        per_unit = ZERO
        if lot_to_amount > ZERO:
            per_unit = (carried_basis / lot_to_amount).quantize(
                Decimal("0.00000001"), rounding=ROUND_HALF_UP
            )

        new_lot = TaxLot(
            wallet_id=to_wallet_id,
            asset_id=to_asset_id,
            amount=str(lot_to_amount),
            remaining_amount=str(lot_to_amount),
            cost_basis_usd=str(carried_basis.quantize(PENNY, rounding=ROUND_HALF_UP)),
            cost_basis_per_unit=str(per_unit),
            acquired_date=consumption.lot.acquired_date,  # preserve original date
            acquisition_tx_id=tx.id,
            source_type=LotSourceType.wrapping_swap.value,
        )
        db.add(new_lot)
        new_lots.append(new_lot)

    db.flush()
    return new_lots
