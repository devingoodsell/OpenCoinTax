"""Lot selection algorithms — FIFO, LIFO, HIFO, Specific ID.

Each algorithm operates on a list of open tax lots and returns a list of
LotConsumption records indicating how much to consume from each lot.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from app.models import TaxLot


@dataclass
class LotConsumption:
    """How much to consume from a single tax lot."""
    lot: TaxLot
    amount: Decimal
    cost_basis_usd: Decimal  # proportional cost basis for this consumption


class InsufficientLotsError(Exception):
    """Raised when disposal amount exceeds available lots."""
    def __init__(self, asset_id: int, wallet_id: int, needed: Decimal, available: Decimal):
        self.asset_id = asset_id
        self.wallet_id = wallet_id
        self.needed = needed
        self.available = available
        super().__init__(
            f"Insufficient lots: need {needed}, have {available} "
            f"(wallet={wallet_id}, asset={asset_id})"
        )


def _consume_lots(sorted_lots: list[TaxLot], disposal_amount: Decimal) -> list[LotConsumption]:
    """Consume lots in the given order until disposal_amount is fully covered.

    Shared logic for FIFO/LIFO/HIFO — only the sort order differs.
    """
    remaining = disposal_amount
    consumptions: list[LotConsumption] = []

    for lot in sorted_lots:
        if remaining <= Decimal("0"):
            break

        lot_remaining = Decimal(lot.remaining_amount)
        if lot_remaining <= Decimal("0"):
            continue

        consume_qty = min(remaining, lot_remaining)
        per_unit = Decimal(lot.cost_basis_per_unit)
        basis = (consume_qty * per_unit).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        consumptions.append(LotConsumption(lot=lot, amount=consume_qty, cost_basis_usd=basis))
        remaining -= consume_qty

    if remaining > Decimal("0"):
        total_available = sum(
            Decimal(l.remaining_amount) for l in sorted_lots if Decimal(l.remaining_amount) > 0
        )
        raise InsufficientLotsError(
            asset_id=sorted_lots[0].asset_id if sorted_lots else 0,
            wallet_id=sorted_lots[0].wallet_id if sorted_lots else 0,
            needed=disposal_amount,
            available=total_available,
        )

    return consumptions


def select_fifo(lots: list[TaxLot], disposal_amount: Decimal) -> list[LotConsumption]:
    """FIFO: consume oldest lots first."""
    sorted_lots = sorted(lots, key=lambda l: l.acquired_date)
    return _consume_lots(sorted_lots, disposal_amount)


def select_lifo(lots: list[TaxLot], disposal_amount: Decimal) -> list[LotConsumption]:
    """LIFO: consume newest lots first."""
    sorted_lots = sorted(lots, key=lambda l: l.acquired_date, reverse=True)
    return _consume_lots(sorted_lots, disposal_amount)


def select_hifo(lots: list[TaxLot], disposal_amount: Decimal) -> list[LotConsumption]:
    """HIFO: consume highest cost-per-unit lots first."""
    sorted_lots = sorted(lots, key=lambda l: Decimal(l.cost_basis_per_unit), reverse=True)
    return _consume_lots(sorted_lots, disposal_amount)


def select_specific_id(
    lots: list[TaxLot],
    selections: list[tuple[int, Decimal]],
) -> list[LotConsumption]:
    """Specific ID: user provides a list of (lot_id, amount) pairs."""
    lot_map = {lot.id: lot for lot in lots}
    consumptions: list[LotConsumption] = []

    for lot_id, amount in selections:
        if lot_id not in lot_map:
            raise ValueError(f"Lot {lot_id} not found in available lots")

        lot = lot_map[lot_id]
        lot_remaining = Decimal(lot.remaining_amount)
        if amount > lot_remaining:
            raise ValueError(
                f"Cannot consume {amount} from lot {lot_id}: only {lot_remaining} remaining"
            )

        per_unit = Decimal(lot.cost_basis_per_unit)
        basis = (amount * per_unit).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        consumptions.append(LotConsumption(lot=lot, amount=amount, cost_basis_usd=basis))

    return consumptions


# Registry for method name -> selector function
LOT_SELECTORS = {
    "fifo": select_fifo,
    "lifo": select_lifo,
    "hifo": select_hifo,
}


def get_lot_selector(method: str):
    """Return the selector function for a given cost basis method name."""
    if method not in LOT_SELECTORS:
        raise ValueError(f"Unknown cost basis method: {method}")
    return LOT_SELECTORS[method]
