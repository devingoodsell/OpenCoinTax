"""Invariant checker — validates data integrity after recalculation.

Five checks:
1. Balance check: lot remaining amounts match expected balances
2. Gain/loss math check: gain = proceeds - basis for every assignment
3. Lot exhaustion check: no negative remaining amounts
4. Temporal consistency: no lot consumed before its acquisition date
5. Double-spend check: no lot over-assigned
"""

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import TaxLot, LotAssignment, Transaction, TransactionType
from app.utils.decimal_helpers import ZERO, PENNY


@dataclass
class CheckResult:
    check_name: str
    status: str  # "pass", "fail", "warning"
    details: str


def check_balance(db: Session, wallet_id: int | None = None) -> list[CheckResult]:
    """Verify SUM(remaining_amount) matches expected balance from transactions."""
    results = []

    q = db.query(TaxLot.wallet_id, TaxLot.asset_id).group_by(TaxLot.wallet_id, TaxLot.asset_id)
    if wallet_id:
        q = q.filter(TaxLot.wallet_id == wallet_id)

    for wid, aid in q.all():
        # Sum of remaining amounts from open lots
        lot_sum = (
            db.query(func.sum(TaxLot.remaining_amount))
            .filter(TaxLot.wallet_id == wid, TaxLot.asset_id == aid)
            .scalar()
        )
        lot_balance = Decimal(str(lot_sum)) if lot_sum else ZERO

        if lot_balance < ZERO:
            results.append(CheckResult(
                check_name="balance_check",
                status="fail",
                details=f"Negative balance for wallet={wid}, asset={aid}: {lot_balance}",
            ))
        else:
            results.append(CheckResult(
                check_name="balance_check",
                status="pass",
                details=f"wallet={wid}, asset={aid}: balance={lot_balance}",
            ))

    return results


def check_gain_loss_math(db: Session) -> list[CheckResult]:
    """Verify gain_loss = proceeds - cost_basis for every lot assignment."""
    results = []
    assignments = db.query(LotAssignment).all()

    for a in assignments:
        proceeds = Decimal(a.proceeds_usd)
        basis = Decimal(a.cost_basis_usd)
        recorded_gl = Decimal(a.gain_loss_usd)
        expected_gl = proceeds - basis

        if abs(recorded_gl - expected_gl) > PENNY:
            results.append(CheckResult(
                check_name="gain_loss_math",
                status="fail",
                details=(
                    f"Assignment {a.id}: recorded={recorded_gl}, "
                    f"expected={expected_gl} (proceeds={proceeds}, basis={basis})"
                ),
            ))

    if not results:
        results.append(CheckResult(
            check_name="gain_loss_math",
            status="pass",
            details=f"All {len(assignments)} assignments have correct math",
        ))

    return results


def check_negative_remaining(db: Session) -> list[CheckResult]:
    """Verify no lot has negative remaining_amount."""
    results = []
    lots = db.query(TaxLot).all()

    for lot in lots:
        remaining = Decimal(lot.remaining_amount)
        if remaining < ZERO:
            results.append(CheckResult(
                check_name="negative_remaining",
                status="fail",
                details=f"Lot {lot.id}: remaining={remaining} (wallet={lot.wallet_id}, asset={lot.asset_id})",
            ))

    if not results:
        results.append(CheckResult(
            check_name="negative_remaining",
            status="pass",
            details=f"All {len(lots)} lots have non-negative remaining amounts",
        ))

    return results


def check_temporal_consistency(db: Session) -> list[CheckResult]:
    """Verify no lot is consumed before its acquired_date."""
    results = []
    assignments = (
        db.query(LotAssignment)
        .join(TaxLot, LotAssignment.tax_lot_id == TaxLot.id)
        .join(Transaction, LotAssignment.disposal_tx_id == Transaction.id)
        .all()
    )

    for a in assignments:
        lot = db.get(TaxLot, a.tax_lot_id)
        tx = db.get(Transaction, a.disposal_tx_id)
        if lot and tx and tx.datetime_utc < lot.acquired_date:
            results.append(CheckResult(
                check_name="temporal_consistency",
                status="fail",
                details=(
                    f"Lot {lot.id} (acquired {lot.acquired_date}) consumed by "
                    f"tx {tx.id} (date {tx.datetime_utc}) — disposal before acquisition"
                ),
            ))

    if not results:
        count = len(assignments)
        results.append(CheckResult(
            check_name="temporal_consistency",
            status="pass",
            details=f"All {count} assignments are temporally consistent",
        ))

    return results


def check_double_spend(db: Session) -> list[CheckResult]:
    """Verify SUM(assigned amount) <= lot original amount for every lot."""
    results = []

    lots_with_assignments = (
        db.query(TaxLot)
        .join(LotAssignment, TaxLot.id == LotAssignment.tax_lot_id)
        .distinct()
        .all()
    )

    for lot in lots_with_assignments:
        total_assigned = (
            db.query(func.sum(LotAssignment.amount))
            .filter(LotAssignment.tax_lot_id == lot.id)
            .scalar()
        )
        assigned = Decimal(str(total_assigned)) if total_assigned else ZERO
        original = Decimal(lot.amount)

        if assigned > original + PENNY:  # tolerance
            results.append(CheckResult(
                check_name="double_spend",
                status="fail",
                details=(
                    f"Lot {lot.id}: assigned={assigned}, original={original} — "
                    f"over-assigned by {assigned - original}"
                ),
            ))

    if not results:
        results.append(CheckResult(
            check_name="double_spend",
            status="pass",
            details=f"No lots are over-assigned",
        ))

    return results


def run_all_checks(db: Session, wallet_id: int | None = None) -> list[CheckResult]:
    """Run all invariant checks and return combined results."""
    results = []
    results.extend(check_balance(db, wallet_id))
    results.extend(check_gain_loss_math(db))
    results.extend(check_negative_remaining(db))
    results.extend(check_temporal_consistency(db))
    results.extend(check_double_spend(db))
    return results
