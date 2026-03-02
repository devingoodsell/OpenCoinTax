from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Asset, LotAssignment, TaxLot, Transaction,
    CostBasisMethod, HoldingPeriod,
)
from app.schemas.tax import (
    GainLossItem,
    GainLossListResponse,
    InvariantCheckResponse,
    InvariantCheckResult,
    MethodComparisonItem,
    MethodComparisonResponse,
    TaxLotResponse,
    TaxSummaryResponse,
)
from app.services.tax_engine import (
    recalculate_all,
    recalculate_for_wallet_asset,
    calculate_for_wallet_asset,
    _find_pairs_for_year,
    _get_transaction_year_range,
)
from app.services.invariant_checker import run_all_checks
from app.services.lot_selector import InsufficientLotsError, select_specific_id
from app.services.whatif import whatif_analysis
from app.utils.decimal_helpers import ZERO, PENNY

router = APIRouter()


@router.post("/recalculate")
def recalculate(year: int | None = None, db: Session = Depends(get_db)):
    """Recalculate cost basis for all wallet/asset pairs across all years."""
    try:
        data = recalculate_all(db, tax_year=year)
    except InsufficientLotsError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    results = data["results"]
    return {
        "pairs_processed": len(results),
        "results": results,
        "errors": data["errors"],
        "error_transaction_count": data["error_transaction_count"],
    }


@router.get("/summary/{year}", response_model=TaxSummaryResponse)
def tax_summary(year: int, db: Session = Depends(get_db)):
    """Calculate an aggregate tax summary for a given year."""
    from app.services.report_generator import TaxSummaryGenerator
    generator = TaxSummaryGenerator(db)
    return generator.generate(year)


@router.get("/gains/{year}", response_model=GainLossListResponse)
def tax_gains(year: int, db: Session = Depends(get_db)):
    """Return lot assignments (realized gains/losses) for the given tax year."""
    assignments = (
        db.query(LotAssignment)
        .filter(LotAssignment.tax_year == year)
        .order_by(LotAssignment.created_at)
        .all()
    )

    items = []
    for a in assignments:
        lot = db.get(TaxLot, a.tax_lot_id)
        tx = db.get(Transaction, a.disposal_tx_id)
        asset = db.get(Asset, lot.asset_id) if lot else None

        items.append(GainLossItem(
            transaction_id=a.disposal_tx_id,
            asset_symbol=asset.symbol if asset else "UNKNOWN",
            amount=a.amount,
            date_acquired=lot.acquired_date if lot else tx.datetime_utc,
            date_sold=tx.datetime_utc if tx else datetime.now(),
            proceeds_usd=a.proceeds_usd,
            cost_basis_usd=a.cost_basis_usd,
            gain_loss_usd=a.gain_loss_usd,
            holding_period=a.holding_period,
        ))

    return GainLossListResponse(items=items, total=len(items))


@router.get("/lots")
def list_lots(asset_id: int | None = None, db: Session = Depends(get_db)):
    """Return tax lots, optionally filtered by asset_id."""
    q = db.query(TaxLot).order_by(TaxLot.acquired_date)
    if asset_id is not None:
        q = q.filter(TaxLot.asset_id == asset_id)

    lots = q.all()
    result = []
    for lot in lots:
        asset = db.get(Asset, lot.asset_id)
        result.append(TaxLotResponse(
            id=lot.id,
            wallet_id=lot.wallet_id,
            asset_id=lot.asset_id,
            asset_symbol=asset.symbol if asset else None,
            amount=lot.amount,
            remaining_amount=lot.remaining_amount,
            cost_basis_usd=lot.cost_basis_usd,
            cost_basis_per_unit=lot.cost_basis_per_unit,
            acquired_date=lot.acquired_date,
            source_type=lot.source_type,
            is_fully_disposed=lot.is_fully_disposed,
        ))
    return {"items": result, "total": len(result)}


@router.post("/validate", response_model=InvariantCheckResponse)
def validate(db: Session = Depends(get_db)):
    """Run all invariant checks on the current data."""
    check_results = run_all_checks(db)
    all_passed = all(r.status == "pass" for r in check_results)
    return InvariantCheckResponse(
        results=[
            InvariantCheckResult(
                check_name=r.check_name,
                status=r.status,
                details=r.details,
            )
            for r in check_results
        ],
        all_passed=all_passed,
    )


@router.get("/compare-methods/{year}", response_model=MethodComparisonResponse)
def compare_methods(year: int, db: Session = Depends(get_db)):
    """Run calculations under fifo, lifo, and hifo to compare outcomes.

    Uses a savepoint for each method so the database is not mutated.
    """
    methods = [
        CostBasisMethod.fifo.value,
        CostBasisMethod.lifo.value,
        CostBasisMethod.hifo.value,
    ]

    # Gather all (wallet_id, asset_id) pairs for the year
    from_pairs = (
        db.query(
            Transaction.from_wallet_id.label("wallet_id"),
            Transaction.from_asset_id.label("asset_id"),
        )
        .filter(
            Transaction.datetime_utc >= datetime(year, 1, 1),
            Transaction.datetime_utc < datetime(year + 1, 1, 1),
            Transaction.from_wallet_id.isnot(None),
            Transaction.from_asset_id.isnot(None),
        )
    )
    to_pairs = (
        db.query(
            Transaction.to_wallet_id.label("wallet_id"),
            Transaction.to_asset_id.label("asset_id"),
        )
        .filter(
            Transaction.datetime_utc >= datetime(year, 1, 1),
            Transaction.datetime_utc < datetime(year + 1, 1, 1),
            Transaction.to_wallet_id.isnot(None),
            Transaction.to_asset_id.isnot(None),
        )
    )
    all_pairs = from_pairs.union(to_pairs).all()
    pairs = {(r.wallet_id, r.asset_id) for r in all_pairs}

    all_years = _get_transaction_year_range(db)
    comparisons: list[MethodComparisonItem] = []

    for method in methods:
        # Use a nested savepoint so we can roll back each method's changes
        nested = db.begin_nested()
        try:
            # Delete all lots and assignments for a clean rebuild
            db.query(LotAssignment).delete()
            db.query(TaxLot).delete()
            db.flush()

            # Process all years from earliest to latest with this method
            for yr in all_years:
                yr_pairs = _find_pairs_for_year(db, yr)
                for wallet_id, asset_id in sorted(yr_pairs):
                    try:
                        calculate_for_wallet_asset(
                            db, wallet_id, asset_id, yr, method=method
                        )
                    except (InsufficientLotsError, Exception):
                        continue

            # Gather results for the target year only
            total_gains = ZERO
            total_losses = ZERO
            st_net = ZERO
            lt_net = ZERO

            new_assignments = (
                db.query(LotAssignment)
                .filter(LotAssignment.tax_year == year)
                .all()
            )
            for a in new_assignments:
                gl = Decimal(a.gain_loss_usd)
                if gl > ZERO:
                    total_gains += gl
                else:
                    total_losses += abs(gl)
                if a.holding_period == HoldingPeriod.short_term.value:
                    st_net += gl
                else:
                    lt_net += gl

        finally:
            nested.rollback()

        def q(val: Decimal) -> str:
            return str(val.quantize(PENNY, rounding=ROUND_HALF_UP))

        comparisons.append(MethodComparisonItem(
            method=method,
            total_gains=q(total_gains),
            total_losses=q(total_losses),
            net_gain_loss=q(total_gains - total_losses),
            short_term_net=q(st_net),
            long_term_net=q(lt_net),
        ))

    return MethodComparisonResponse(tax_year=year, comparisons=comparisons)


@router.post("/backfill-koinly-values")
def backfill_koinly_values(db: Session = Depends(get_db)):
    """Backfill from_value_usd/to_value_usd on koinly-imported transactions, then recalculate."""
    from app.services.koinly_import import backfill_koinly_usd_values
    updated = backfill_koinly_usd_values(db)
    db.commit()
    data = recalculate_all(db)
    return {
        "transactions_backfilled": updated,
        "pairs_processed": len(data["results"]),
        "error_transaction_count": data["error_transaction_count"],
    }


@router.post("/reclassify-deposits")
def reclassify_deposits(
    dry_run: bool = True,
    db: Session = Depends(get_db),
):
    """Reclassify crypto_deposit transactions to staking_reward or interest.

    Uses heuristics to detect staking rewards and interest income among
    transactions that were imported with the generic 'crypto_deposit' label:

    - Liquid staking token deposits (STETH, stATOM, etc.) → staking_reward
    - Deposits with description containing 'interest' → interest
    - High-frequency small deposits of the same asset to the same wallet → staking_reward

    Set dry_run=false to apply changes.  Always recalculates after applying.
    """
    from app.services.deposit_reclassifier import reclassify_crypto_deposits

    changes = reclassify_crypto_deposits(db, dry_run=dry_run)

    if not dry_run:
        db.commit()
        data = recalculate_all(db)
        return {
            "applied": True,
            "changes": changes,
            "pairs_processed": len(data["results"]),
            "error_transaction_count": data["error_transaction_count"],
        }

    return {"applied": False, "changes": changes}


@router.get("/whatif/{transaction_id}")
def whatif(transaction_id: int, db: Session = Depends(get_db)):
    """Run what-if analysis for a disposal transaction.

    Compares FIFO, LIFO, HIFO outcomes without modifying data.
    """
    try:
        result = whatif_analysis(db, transaction_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return result


@router.post("/specific-id/{transaction_id}")
def apply_specific_id(
    transaction_id: int,
    selections: list[dict],
    db: Session = Depends(get_db),
):
    """Apply specific lot identification for a disposal transaction.

    Body: list of {"lot_id": int, "amount": str} objects.
    Deletes existing lot assignments for this transaction and creates new ones.
    """
    tx = db.get(Transaction, transaction_id)
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    wallet_id = tx.from_wallet_id
    asset_id = tx.from_asset_id
    if not wallet_id or not asset_id:
        raise HTTPException(status_code=400, detail="Transaction is not a disposal")

    disposal_amount = Decimal(tx.from_amount) if tx.from_amount else ZERO
    proceeds_usd = Decimal(tx.from_value_usd) if tx.from_value_usd else ZERO
    if tx.fee_value_usd and tx.type in ("sell", "cost"):
        proceeds_usd -= Decimal(tx.fee_value_usd)

    # Parse selections
    parsed = [(s["lot_id"], Decimal(str(s["amount"]))) for s in selections]
    total_selected = sum(amt for _, amt in parsed)
    if total_selected != disposal_amount:
        raise HTTPException(
            status_code=422,
            detail=f"Selected amount {total_selected} != disposal amount {disposal_amount}",
        )

    # Get open lots
    open_lots = (
        db.query(TaxLot)
        .filter(
            TaxLot.wallet_id == wallet_id,
            TaxLot.asset_id == asset_id,
            TaxLot.is_fully_disposed == False,
        )
        .all()
    )

    try:
        consumptions = select_specific_id(open_lots, parsed)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # Delete existing assignments for this transaction
    existing = (
        db.query(LotAssignment)
        .filter(LotAssignment.disposal_tx_id == transaction_id)
        .all()
    )
    # Restore lot remaining amounts before deleting
    for a in existing:
        lot = db.get(TaxLot, a.tax_lot_id)
        if lot:
            lot.remaining_amount = str(
                Decimal(lot.remaining_amount) + Decimal(a.amount)
            )
            lot.is_fully_disposed = False
        db.delete(a)
    db.flush()

    # Create new assignments from specific ID selection
    total_consumed = sum(c.amount for c in consumptions)
    new_assignments = []
    for c in consumptions:
        proportion = c.amount / total_consumed if total_consumed > ZERO else ZERO
        lot_proceeds = (proceeds_usd * proportion).quantize(PENNY, rounding=ROUND_HALF_UP)
        lot_basis = c.cost_basis_usd
        gl = (lot_proceeds - lot_basis).quantize(PENNY, rounding=ROUND_HALF_UP)

        delta = (tx.datetime_utc - c.lot.acquired_date).days
        hp = HoldingPeriod.long_term.value if delta > 365 else HoldingPeriod.short_term.value

        assignment = LotAssignment(
            disposal_tx_id=transaction_id,
            tax_lot_id=c.lot.id,
            amount=str(c.amount),
            cost_basis_usd=str(lot_basis),
            proceeds_usd=str(lot_proceeds),
            gain_loss_usd=str(gl),
            holding_period=hp,
            cost_basis_method="specific_id",
            tax_year=tx.datetime_utc.year,
        )
        db.add(assignment)

        # Update lot remaining
        new_remaining = Decimal(c.lot.remaining_amount) - c.amount
        c.lot.remaining_amount = str(new_remaining)
        if new_remaining <= ZERO:
            c.lot.is_fully_disposed = True

        new_assignments.append({
            "lot_id": c.lot.id,
            "amount": str(c.amount),
            "cost_basis_usd": str(lot_basis),
            "proceeds_usd": str(lot_proceeds),
            "gain_loss_usd": str(gl),
            "holding_period": hp,
        })

    db.commit()
    return {"transaction_id": transaction_id, "assignments": new_assignments}
