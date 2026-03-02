"""What-if analysis — compare gain/loss for a single disposal under each method.

Takes a disposal transaction and simulates lot selection under FIFO, LIFO, HIFO
without modifying the database. Returns per-method breakdown.
"""

from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.models import TaxLot, Transaction, LotAssignment, HoldingPeriod
from app.services.lot_selector import (
    select_fifo, select_lifo, select_hifo, LotConsumption, InsufficientLotsError,
)
from app.utils.decimal_helpers import ZERO, PENNY


def _holding_period(acquired: datetime, disposed: datetime, threshold_days: int = 365) -> str:
    delta = (disposed - acquired).days
    if delta > threshold_days:
        return HoldingPeriod.long_term.value
    return HoldingPeriod.short_term.value


def _simulate_method(
    lots: list[TaxLot],
    disposal_amount: Decimal,
    proceeds_usd: Decimal,
    disposal_date: datetime,
    selector,
) -> dict:
    """Run a lot selection method and compute the resulting gain/loss breakdown."""
    try:
        consumptions = selector(lots, disposal_amount)
    except InsufficientLotsError:
        return {
            "error": "Insufficient lots",
            "lots_used": [],
            "total_cost_basis": "0.00",
            "total_proceeds": str(proceeds_usd.quantize(PENNY, rounding=ROUND_HALF_UP)),
            "total_gain_loss": str(proceeds_usd.quantize(PENNY, rounding=ROUND_HALF_UP)),
            "short_term_gain_loss": "0.00",
            "long_term_gain_loss": "0.00",
        }

    total_consumed = sum(c.amount for c in consumptions)
    lots_used = []
    total_basis = ZERO
    st_gl = ZERO
    lt_gl = ZERO

    for c in consumptions:
        proportion = c.amount / total_consumed if total_consumed > ZERO else ZERO
        lot_proceeds = (proceeds_usd * proportion).quantize(PENNY, rounding=ROUND_HALF_UP)
        lot_basis = c.cost_basis_usd
        gl = lot_proceeds - lot_basis
        hp = _holding_period(c.lot.acquired_date, disposal_date)

        if hp == HoldingPeriod.short_term.value:
            st_gl += gl
        else:
            lt_gl += gl

        total_basis += lot_basis

        lots_used.append({
            "lot_id": c.lot.id,
            "acquired_date": c.lot.acquired_date.isoformat(),
            "amount": str(c.amount),
            "cost_basis_per_unit": c.lot.cost_basis_per_unit,
            "cost_basis_usd": str(lot_basis),
            "proceeds_usd": str(lot_proceeds),
            "gain_loss_usd": str(gl.quantize(PENNY, rounding=ROUND_HALF_UP)),
            "holding_period": hp,
        })

    total_gl = (proceeds_usd - total_basis).quantize(PENNY, rounding=ROUND_HALF_UP)

    return {
        "error": None,
        "lots_used": lots_used,
        "total_cost_basis": str(total_basis.quantize(PENNY, rounding=ROUND_HALF_UP)),
        "total_proceeds": str(proceeds_usd.quantize(PENNY, rounding=ROUND_HALF_UP)),
        "total_gain_loss": str(total_gl),
        "short_term_gain_loss": str(st_gl.quantize(PENNY, rounding=ROUND_HALF_UP)),
        "long_term_gain_loss": str(lt_gl.quantize(PENNY, rounding=ROUND_HALF_UP)),
    }


def whatif_analysis(
    db: Session,
    disposal_tx_id: int,
) -> dict:
    """Run what-if analysis for a disposal transaction.

    Returns comparison of FIFO, LIFO, and HIFO outcomes.
    Does NOT modify the database.
    """
    tx = db.get(Transaction, disposal_tx_id)
    if not tx:
        raise ValueError(f"Transaction {disposal_tx_id} not found")

    wallet_id = tx.from_wallet_id
    asset_id = tx.from_asset_id
    if not wallet_id or not asset_id:
        raise ValueError("Transaction is not a disposal (no from_wallet/from_asset)")

    disposal_amount = Decimal(tx.from_amount) if tx.from_amount else ZERO
    proceeds_usd = Decimal(tx.from_value_usd) if tx.from_value_usd else ZERO

    # Fee reduces proceeds for sells
    if tx.fee_value_usd and tx.type in ("sell", "cost"):
        proceeds_usd -= Decimal(tx.fee_value_usd)

    # Get all open lots (snapshot — don't modify)
    open_lots = (
        db.query(TaxLot)
        .filter(
            TaxLot.wallet_id == wallet_id,
            TaxLot.asset_id == asset_id,
            TaxLot.is_fully_disposed == False,
        )
        .order_by(TaxLot.acquired_date)
        .all()
    )

    methods = {
        "fifo": select_fifo,
        "lifo": select_lifo,
        "hifo": select_hifo,
    }

    results = {}
    best_method = None
    best_gl = None

    for method_name, selector in methods.items():
        result = _simulate_method(
            open_lots, disposal_amount, proceeds_usd, tx.datetime_utc, selector
        )
        results[method_name] = result

        if result["error"] is None:
            gl = Decimal(result["total_gain_loss"])
            # "Best" = lowest tax liability (most negative or least positive)
            if best_gl is None or gl < best_gl:
                best_gl = gl
                best_method = method_name

    return {
        "transaction_id": disposal_tx_id,
        "disposal_amount": str(disposal_amount),
        "proceeds_usd": str(proceeds_usd.quantize(PENNY, rounding=ROUND_HALF_UP)),
        "methods": results,
        "most_tax_efficient": best_method,
    }
